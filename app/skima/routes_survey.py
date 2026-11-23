"""試用テスト：アンケートと結果のまとめ。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import CurrentUser, current_user, require_teacher
from .db import get_db
from .models import Application, Job, Survey
from .results import QUESTIONS, SCALE, jobs_csv, summarize
from .web import render

router = APIRouter()


def _can_answer(db: Session, user: CurrentUser | None, job_id: int) -> Job:
    """生産者は自分が公開した求人、高校生は参加が決まった求人についてだけ答えられる。"""
    job = db.get(Job, job_id)
    if job is None or job.status == "draft" or user is None:
        raise HTTPException(404, "見つかりません")
    if user.role == "producer" and job.producer_id == user.id:
        return job
    if user.role == "student":
        app = db.scalar(select(Application).where(Application.job_id == job_id, Application.student_id == user.id))
        if app and app.status == "confirmed":
            return job
    raise HTTPException(404, "見つかりません")


@router.get("/survey/{job_id}")
def survey_page(job_id: int, request: Request, db: Session = Depends(get_db)):
    user = current_user(request)
    job = _can_answer(db, user, job_id)
    answered = db.scalar(
        select(Survey).where(Survey.role == user.role, Survey.respondent_id == user.id, Survey.job_id == job_id)
    )
    return render(request, "survey.html", job=job, questions=QUESTIONS[user.role], scale=SCALE, answered=answered)


class Answer(BaseModel):
    q1: int = Field(ge=1, le=5)
    q2: int = Field(ge=1, le=5)
    q3: int = Field(ge=1, le=5)
    comment: str | None = Field(None, max_length=500)


@router.post("/api/survey/{job_id}")
def answer_survey(job_id: int, answer: Answer, request: Request, db: Session = Depends(get_db)):
    user = current_user(request)
    _can_answer(db, user, job_id)
    row = db.scalar(
        select(Survey).where(Survey.role == user.role, Survey.respondent_id == user.id, Survey.job_id == job_id)
    )
    if row is None:  # 1つの求人につき1人1回。もう一度答えたら上書き
        row = Survey(role=user.role, respondent_id=user.id, job_id=job_id, q1=0, q2=0, q3=0)
        db.add(row)
    row.q1, row.q2, row.q3 = answer.q1, answer.q2, answer.q3
    row.comment = (answer.comment or "").strip() or None
    db.commit()
    return {"ok": True}


@router.get("/teacher/results")
def results_page(request: Request, user: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)):
    return render(request, "results.html", s=summarize(db), questions=QUESTIONS)


@router.get("/teacher/results.csv")
def results_csv(user: CurrentUser = Depends(require_teacher), db: Session = Depends(get_db)):
    return Response(
        jobs_csv(db), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="skima_results.csv"'},
    )
