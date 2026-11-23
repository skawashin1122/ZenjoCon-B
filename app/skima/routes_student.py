"""高校生の画面とAPI：お知らせ・案内された求人・参加／キャンセル・空き時間の登録。"""
from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import stats
from .applications import ApplyError, cancel, confirm, offers_for
from .auth import current_user, get_student
from .config import Settings, get_settings
from .db import get_db
from .jobs import date_text, time_text
from .models import Application, Job, Notification, Student
from .web import render

router = APIRouter()


@router.get("/student")
def student_home(request: Request, student: Student = Depends(get_student), db: Session = Depends(get_db)):
    notices = list(
        db.scalars(
            select(Notification)
            .where(Notification.recipient_type == "student", Notification.recipient_id == student.id)
            .order_by(Notification.id.desc())
            .limit(10)
        )
    )
    upcoming = sorted(
        (s for s in student.available_slots or [] if s.get("date", "") >= date.today().isoformat()),
        key=lambda s: (s["date"], s["start"]),
    )
    return render(
        request, "student.html",
        student=student, offers=offers_for(db, student), notices=notices,
        slots=upcoming[:7], date_text=date_text, time_text=time_text,
        approved=bool(student.approval and student.approval.is_approved),
    )


@router.get("/jobs/{job_id}")
def job_card(job_id: int, request: Request, db: Session = Depends(get_db)):
    """求人カード。見られるのは、案内を受け取った学生・その求人の生産者・教員だけ。"""
    job = db.get(Job, job_id)
    user = current_user(request)
    if job is None or job.status == "draft" or user is None:
        raise HTTPException(404, "求人が見つかりません")
    app = None
    if user.role == "student":
        app = db.scalar(select(Application).where(Application.job_id == job.id, Application.student_id == user.id))
        if app is None:
            raise HTTPException(404, "求人が見つかりません")
    elif user.role == "producer" and job.producer_id != user.id:
        raise HTTPException(404, "求人が見つかりません")
    return render(
        request, "job.html",
        job=job, app=app,
        date=date_text(job.work_date),
        time=f"{time_text(job.start_time)}〜{time_text(job.end_time)}",
        hint=stats.hint_for(job.industry, seed=job.id), closing=stats.CLOSING, source=stats.SOURCE,
    )


def _own_application(db: Session, app_id: int, student: Student) -> Application:
    app = db.get(Application, app_id)
    if app is None or app.student_id != student.id:
        raise HTTPException(404, "案内が見つかりません")
    return app


@router.post("/api/applications/{app_id}/confirm")
def confirm_application(
    app_id: int, student: Student = Depends(get_student),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
):
    try:
        app = confirm(db, settings, _own_application(db, app_id, student), student)
    except ApplyError as e:
        raise HTTPException(409, e.message)
    return {"status": app.status}


@router.post("/api/applications/{app_id}/cancel")
def cancel_application(
    app_id: int, student: Student = Depends(get_student),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
):
    try:
        app = cancel(db, settings, _own_application(db, app_id, student), student)
    except ApplyError as e:
        raise HTTPException(409, e.message)
    return {"status": app.status}


class Slot(BaseModel):
    date: str
    start: str
    end: str

    @field_validator("date")
    @classmethod
    def _date(cls, v: str) -> str:
        if date.fromisoformat(v) < date.today():
            raise ValueError("過去の日付です")
        return v

    @field_validator("start", "end")
    @classmethod
    def _time(cls, v: str) -> str:
        return time.fromisoformat(v).strftime("%H:%M")


@router.post("/api/me/slots")
def add_slot(slot: Slot, student: Student = Depends(get_student), db: Session = Depends(get_db)):
    if slot.end <= slot.start:
        raise HTTPException(422, "終わりの時刻は、始まりより後にしてください")
    slots = [s for s in (student.available_slots or []) if s != slot.model_dump()]
    student.available_slots = sorted(slots + [slot.model_dump()], key=lambda s: (s["date"], s["start"]))
    db.commit()
    return {"slots": student.available_slots}


@router.delete("/api/me/slots")
def delete_slot(slot: Slot, student: Student = Depends(get_student), db: Session = Depends(get_db)):
    student.available_slots = [s for s in (student.available_slots or []) if s != slot.model_dump()]
    db.commit()
    return {"slots": student.available_slots}
