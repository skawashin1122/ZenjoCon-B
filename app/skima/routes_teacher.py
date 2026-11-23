"""教員の画面とAPI：保護者同意・学校許可の確認、参加の承認、だれがいつどこで働くかの確認。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import CurrentUser, require_teacher
from .config import Settings, get_settings
from .db import get_db
from .demo import refresh_slots, reset_for_demo
from .jobs import date_text, time_text
from .models import Application, Approval, Job, Student
from .web import render

router = APIRouter()


def _approval(db: Session, student_id: int) -> Approval:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(404, "生徒が見つかりません")
    if student.approval is None:
        student.approval = Approval(student_id=student.id)
        db.flush()
    return student.approval


def _status(a: Approval) -> dict:
    return {
        "parent_consent": a.parent_consent,
        "school_permission": a.school_permission,
        "approved": a.is_approved,
    }


@router.get("/teacher")
def teacher_home(request: Request, user: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)):
    students = list(db.scalars(select(Student).order_by(Student.id)))
    schedule = list(
        db.scalars(
            select(Application)
            .join(Job)
            .where(Application.status == "confirmed")
            .order_by(Job.work_date, Job.start_time)
        )
    )
    return render(request, "teacher.html", students=students, schedule=schedule, date_text=date_text, time_text=time_text)


class Checks(BaseModel):
    parent_consent: bool
    school_permission: bool


@router.post("/api/teacher/students/{student_id}/checks")
def set_checks(student_id: int, checks: Checks, user: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)):
    """保護者の同意書・学校の許可を確認したら、チェックを付ける。どちらかを外すと承認も取り消す。"""
    a = _approval(db, student_id)
    a.parent_consent = checks.parent_consent
    a.school_permission = checks.school_permission
    if not (a.parent_consent and a.school_permission):
        a.approved_at = None
        a.approved_by = None
    db.commit()
    return _status(a)


@router.post("/api/teacher/students/{student_id}/approve")
def approve(student_id: int, user: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)):
    """両方そろった生徒だけ承認できる。"""
    a = _approval(db, student_id)
    if not (a.parent_consent and a.school_permission):
        raise HTTPException(422, "保護者の同意と学校の許可の両方が必要です")
    a.approved_at = datetime.now()
    a.approved_by = user.name
    db.commit()
    return _status(a)


@router.post("/api/teacher/students/{student_id}/revoke")
def revoke(student_id: int, user: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)):
    a = _approval(db, student_id)
    a.approved_at = None
    a.approved_by = None
    db.commit()
    return _status(a)


# ---------------- 本番デモの準備 ----------------

@router.post("/api/teacher/demo/refresh-slots")
def demo_refresh_slots(user: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)):
    """デモ生徒の空き時間を「今日から2週間」に更新する（記録は消さない）。"""
    return {"students": refresh_slots(db)}


@router.post("/api/teacher/demo/reset")
def demo_reset(
    user: CurrentUser = Depends(require_teacher),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """求人・案内・通知・アンケートを消して、デモの最初の状態に戻す。DEMO_MODE=true のときだけ。"""
    if not settings.demo_mode:
        raise HTTPException(403, "DEMO_MODE が false のため使えません")
    return reset_for_demo(db)
