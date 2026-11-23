"""スキマ日南ファーム＆シー：Webアプリの入口。

起動: uvicorn skima.main:app --reload
"""
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import ai, rules, stats
from .config import Settings, get_settings
from .db import Base, SessionLocal, engine, get_db
from .jobs import apply_draft, date_text, draft_from_job, speech_text, time_text
from .models import Approval, Job, Producer, Student

logging.basicConfig(level=logging.INFO)
BASE_DIR = Path(__file__).parent
DEMO_PRODUCER_ID = 1  # ログイン機能は第2週。それまではデモ用の生産者1人で動かす


def seed(db: Session) -> None:
    """デモ用の架空データ（実在の人の情報は入れない）。"""
    if db.get(Producer, DEMO_PRODUCER_ID):
        return
    db.add(Producer(id=DEMO_PRODUCER_ID, name="デモ農家", area="北郷"))
    students = [
        Student(nickname="生徒A", grade=2, area="北郷", experience_count=1),
        Student(nickname="生徒B", grade=2, area="飫肥", experience_count=0),
        Student(nickname="生徒C", grade=1, area="南郷", experience_count=0),
    ]
    db.add_all(students)
    db.flush()
    db.add_all(
        [
            Approval(student_id=students[0].id, parent_consent=True, school_permission=True,
                     approved_by="デモ教員", approved_at=datetime.now()),
            Approval(student_id=students[1].id, parent_consent=True, school_permission=False),
            Approval(student_id=students[2].id, parent_consent=False, school_permission=False),
        ]
    )
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="スキマ日南ファーム＆シー", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# ---------------- 共通処理 ----------------

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


def get_own_job(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.producer_id != DEMO_PRODUCER_ID:
        raise HTTPException(404, "求人が見つかりません")
    return job


# ---------------- 画面 ----------------

@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/producer")


@app.get("/producer", response_class=HTMLResponse)
def producer_home(request: Request, settings: Settings = Depends(get_settings)):
    return templates.TemplateResponse(request, "producer.html", {"mock_ai": settings.use_mock_ai})


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_card(job_id: int, request: Request, db: Session = Depends(get_db)):
    """学生が見る求人カード（LINEのリンク先）。公開済みのものだけ表示する。"""
    job = db.get(Job, job_id)
    if job is None or job.status != "published":
        raise HTTPException(404, "求人が見つかりません")
    return templates.TemplateResponse(
        request,
        "job.html",
        {
            "job": job,
            "date": date_text(job.work_date),
            "time": f"{time_text(job.start_time)}〜{time_text(job.end_time)}",
            "hint": stats.hint_for(job.industry, seed=job.id),
            "closing": stats.CLOSING,
            "source": stats.SOURCE,
        },
    )


# ---------------- API ----------------

@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/drafts")
async def create_draft(
    photo: UploadFile | None = File(None),
    audio: UploadFile | None = File(None),
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
    job = Job(producer_id=DEMO_PRODUCER_ID, status="draft")
    apply_draft(job, draft)
    db.add(job)
    db.commit()
    return draft_response(job, settings)


@app.post("/api/jobs/{job_id}/answer")
async def answer_question(
    job_id: int,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """② 足りない項目を声で答える → 下書きを更新する。"""
    job = get_own_job(db, job_id)
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


@app.post("/api/jobs/{job_id}/publish")
def publish(job_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """③ 生産者が「これで公開」を押した。公開前にもう一度ルールで確認する。"""
    job = get_own_job(db, job_id)
    draft = draft_from_job(job)
    if rules.missing_fields(draft) or rules.validate_for_publish(draft, settings.min_wage):
        raise HTTPException(422, "まだ公開できません")
    if job.status == "draft":
        job.status = "published"
        job.published_at = datetime.now()
        db.commit()
    blockers = rules.high_school_blockers(job.start_time, job.end_time, job.max_weight_kg, job.location_type)
    return {
        "job_id": job.id,
        "status": job.status,
        "url": f"/jobs/{job.id}",
        "visible_to_high_school": not blockers,
        "high_school_blockers": blockers,
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return draft_response(get_own_job(db, job_id), settings)
