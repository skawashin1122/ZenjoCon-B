"""生産者の画面とAPI：写真＋声 → 下書き → 聞き直し → 公開 → 案内を送る。"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai, rules
from .applications import send_offers
from .auth import get_producer
from .config import Settings, get_settings
from .db import get_db
from .jobs import apply_draft, date_text, draft_from_job, speech_text, time_text
from .models import Job, Notification, Producer
from .web import render

router = APIRouter()


async def read_upload(file: UploadFile | None, kind: str, settings: Settings) -> ai.Media | None:
    """アップロードされたファイルを確認して読み込む。ファイルはディスクに保存しない。"""
    if file is None or not file.filename:
        return None
    mime = (file.content_type or "").split(";")[0]
    if not mime.startswith(kind + "/"):
        raise HTTPException(400, f"{kind} のファイルではありません")
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "ファイルが大きすぎます")
    if not data:
        return None
    return ai.Media(data=data, mime_type=mime)


def draft_response(job: Job, settings: Settings) -> dict:
    """画面に返す内容：下書き・足りない項目・質問・エラー・読み上げ文。"""
    draft = draft_from_job(job)
    missing = rules.missing_fields(draft)
    errors = [e.message for e in rules.validate_for_publish(draft, settings.min_wage)]
    question = rules.follow_up_question(missing)
    speech = speech_text(draft)
    if errors:
        speech += " " + " ".join(errors)
    elif question:
        speech += " " + question
    return {
        "job_id": job.id,
        "status": job.status,
        "draft": draft.model_dump(mode="json"),
        "display": {
            "date": date_text(job.work_date),
            "time": f"{time_text(job.start_time)}〜{time_text(job.end_time)}",
        },
        "missing": missing,
        "question": question,
        "errors": errors,
        "can_publish": not missing and not errors,
        "speech": speech,
        "mock_ai": settings.use_mock_ai,
    }


def own_job(db: Session, producer: Producer, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.producer_id != producer.id:
        raise HTTPException(404, "求人が見つかりません")
    return job


@router.get("/producer")
def producer_home(request: Request, producer: Producer = Depends(get_producer), db: Session = Depends(get_db)):
    jobs = list(
        db.scalars(
            select(Job).where(Job.producer_id == producer.id, Job.status != "draft").order_by(Job.created_at.desc()).limit(5)
        )
    )
    notices = list(
        db.scalars(
            select(Notification)
            .where(Notification.recipient_type == "producer", Notification.recipient_id == producer.id)
            .order_by(Notification.id.desc())
            .limit(5)
        )
    )
    return render(request, "producer.html", jobs=jobs, notices=notices, date_text=date_text)


@router.post("/api/drafts")
async def create_draft(
    photo: UploadFile | None = File(None),
    audio: UploadFile | None = File(None),
    producer: Producer = Depends(get_producer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """① 写真＋音声 → AIで下書きを作る。"""
    image = await read_upload(photo, "image", settings)
    voice = await read_upload(audio, "audio", settings)
    if image is None and voice is None:
        raise HTTPException(400, "写真か声を送ってください")
    try:
        draft = ai.generate_draft(settings, image, voice, date.today())
    except ai.AIError:
        raise HTTPException(502, "うまく聞き取れませんでした。もう一度話してください。")
    # 写真・音声はここで使い終わり。保存せずに捨てる（プライバシー保護）
    job = Job(producer_id=producer.id, status="draft")
    apply_draft(job, draft)
    db.add(job)
    db.commit()
    return draft_response(job, settings)


@router.post("/api/jobs/{job_id}/answer")
async def answer_question(
    job_id: int,
    audio: UploadFile = File(...),
    producer: Producer = Depends(get_producer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """② 足りない項目を声で答える → 下書きを更新する。"""
    job = own_job(db, producer, job_id)
    if job.status != "draft":
        raise HTTPException(409, "公開済みの求人は変更できません")
    voice = await read_upload(audio, "audio", settings)
    if voice is None:
        raise HTTPException(400, "声を送ってください")
    try:
        draft = ai.refine_draft(settings, draft_from_job(job), voice, date.today())
    except ai.AIError:
        raise HTTPException(502, "うまく聞き取れませんでした。もう一度話してください。")
    apply_draft(job, draft)
    db.commit()
    return draft_response(job, settings)


@router.post("/api/jobs/{job_id}/publish")
def publish(
    job_id: int,
    producer: Producer = Depends(get_producer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """③ 生産者が「これで公開」を押した。公開前にもう一度ルールで確認し、条件に合う学生に案内する。"""
    job = own_job(db, producer, job_id)
    draft = draft_from_job(job)
    if rules.missing_fields(draft) or rules.validate_for_publish(draft, settings.min_wage):
        raise HTTPException(422, "まだ公開できません")
    offered = 0
    if job.status == "draft":
        job.status = "published"
        job.published_at = datetime.now()
        db.flush()
        offered = len(send_offers(db, settings, job))
        db.commit()
    blockers = rules.high_school_blockers(job.start_time, job.end_time, job.max_weight_kg, job.location_type)
    return {
        "job_id": job.id,
        "status": job.status,
        "url": f"/jobs/{job.id}",
        "offered": offered,
        "visible_to_high_school": not blockers,
        "high_school_blockers": blockers,
    }


@router.get("/api/jobs/{job_id}")
def get_job(
    job_id: int,
    producer: Producer = Depends(get_producer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return draft_response(own_job(db, producer, job_id), settings)
