"""案内・参加確定（先着）・キャンセルの処理。"""
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import Settings
from .jobs import date_text, time_text
from .matching import NOTIFY_FACTOR, rank_candidates
from .models import Application, Job, Student
from .notify import notify


def job_summary(job: Job) -> str:
    return f"{job.title}\n{date_text(job.work_date)} {time_text(job.start_time)}〜{time_text(job.end_time)}\n時給{job.hourly_wage:,}円・{job.area}地区"


def send_offers(db: Session, settings: Settings, job: Job, limit: int | None = None) -> list[Application]:
    """スコアの高い学生から順に、案内を送る。"""
    if limit is None:
        limit = max(job.headcount or 1, 1) * NOTIFY_FACTOR
    sent: list[Application] = []
    for c in rank_candidates(db, job)[:limit]:
        app = Application(job_id=job.id, student_id=c.student.id, status="notified", score=c.score)
        db.add(app)
        notify(db, settings, c.student, "【スキマ日南】近くでお手伝いの募集があります\n" + job_summary(job), f"/jobs/{job.id}")
        sent.append(app)
    return sent


class ApplyError(Exception):
    def __init__(self, message: str):
        self.message = message


def confirm(db: Session, settings: Settings, app: Application, student: Student) -> Application:
    """学生が「参加する」を押した。先着で確定する。"""
    if app.student_id != student.id:
        raise ApplyError("この案内は見つかりません")
    if app.status == "confirmed":
        return app
    if app.status != "notified":
        raise ApplyError("この案内は受け付けできません")

    # 「公開中で、確定人数が定員未満のときだけ、確定人数を1増やす」を1つの命令で行う。
    # 2人が同時に押しても、データベースが順番に処理するので定員を超えない。
    result = db.execute(
        update(Job)
        .where(Job.id == app.job_id, Job.status == "published", Job.confirmed_count < Job.headcount)
        .values(confirmed_count=Job.confirmed_count + 1)
    )
    if result.rowcount != 1:
        db.rollback()
        raise ApplyError("ごめんなさい、定員に達したため締め切りました")

    job = db.get(Job, app.job_id)
    db.refresh(job)
    app.status = "confirmed"
    app.confirmed_at = datetime.now()
    if job.confirmed_count >= job.headcount:
        job.status = "closed"  # 定員になったので締め切る
    notify(
        db, settings, job.producer,
        f"【スキマ日南】参加が決まりました（{job.confirmed_count}/{job.headcount}人）\n"
        f"{student.nickname}さん（{student.grade}年）\n{job.title} {date_text(job.work_date)}",
        None,
    )
    db.commit()
    return app


def cancel(db: Session, settings: Settings, app: Application, student: Student) -> Application:
    """学生が参加をキャンセルした。空いた枠は、次の順位の人に案内する。"""
    if app.student_id != student.id:
        raise ApplyError("この案内は見つかりません")
    if app.status != "confirmed":
        raise ApplyError("参加が確定していないので、キャンセルできません")

    job = db.get(Job, app.job_id)
    app.status = "cancelled"
    job.confirmed_count = max(job.confirmed_count - 1, 0)
    if job.status == "closed":
        job.status = "published"  # 枠が空いたので募集を再開
    notify(db, settings, job.producer, f"【スキマ日南】{student.nickname}さんが参加をキャンセルしました\n{job.title}", None)
    db.flush()
    send_offers(db, settings, job, limit=1)  # 次の順位の人へ
    db.commit()
    return app


def offers_for(db: Session, student: Student) -> list[Application]:
    return list(
        db.scalars(
            select(Application)
            .where(Application.student_id == student.id, Application.status.in_(["notified", "confirmed"]))
            .order_by(Application.created_at.desc())
        )
    )
