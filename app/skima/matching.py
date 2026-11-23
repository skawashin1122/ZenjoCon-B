"""安全マッチング：求人に合う高校生を「絞り込み → スコア計算 → 並べ替え」で選ぶ。

1. 絞り込み（1つでも満たさなければ対象外）
   - 教員の承認がある（＝保護者同意＋学校許可）
   - 作業が 5〜22時・15kg以下・陸上（rules.high_school_blockers）
   - 学生の空き時間に、作業の時間がすっぽり入る
2. スコア = 近さ点（同じ地区3／となりの地区2／それ以外1）
          + 経験点（経験あり1）
          + 初心者点（初心者歓迎の求人で、経験0回なら1）
3. スコアの高い順に並べる（同点なら登録の早い順）
"""
from dataclasses import dataclass
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import rules
from .models import Application, Job, Student

# 日南市内の地区のとなり合い（おおよそ）。※地図で確認して直すこと
NEIGHBORS: dict[str, set[str]] = {
    "北郷": {"飫肥", "東郷"},
    "飫肥": {"北郷", "酒谷", "吾田", "東郷"},
    "酒谷": {"飫肥"},
    "吾田": {"飫肥", "油津", "東郷", "大窪"},
    "油津": {"吾田", "細田"},
    "東郷": {"北郷", "飫肥", "吾田", "鵜戸"},
    "鵜戸": {"東郷"},
    "細田": {"油津", "南郷"},
    "大窪": {"吾田", "南郷"},
    "南郷": {"細田", "大窪"},
}
AREAS = list(NEIGHBORS)

# 最初に案内を送る人数 = 募集人数 × この数（全員が応募するとは限らないため）
NOTIFY_FACTOR = 2


@dataclass
class Candidate:
    student: Student
    score: int


def distance_points(a: str | None, b: str | None) -> int:
    if not a or not b:
        return 1
    if a == b:
        return 3
    if b in NEIGHBORS.get(a, set()):
        return 2
    return 1


def slot_covers(slots: list[dict], work_date: date | None, start: time | None, end: time | None) -> bool:
    """学生の空き時間のどれかに、作業の時間がすっぽり入るか。"""
    if not (work_date and start and end):
        return False
    for s in slots or []:
        try:
            same_day = date.fromisoformat(s["date"]) == work_date
            fits = time.fromisoformat(s["start"]) <= start and end <= time.fromisoformat(s["end"])
        except (KeyError, ValueError, TypeError):
            continue
        if same_day and fits:
            return True
    return False


def exclusion_reasons(student: Student, job: Job) -> list[str]:
    """この学生にこの求人を案内できない理由（空なら案内してよい）。"""
    reasons: list[str] = []
    if student.approval is None or not student.approval.is_approved:
        reasons.append("教員の承認がない")
    reasons += rules.high_school_blockers(job.start_time, job.end_time, job.max_weight_kg, job.location_type)
    if not slot_covers(student.available_slots, job.work_date, job.start_time, job.end_time):
        reasons.append("空き時間と合わない")
    return reasons


def score(student: Student, job: Job) -> int:
    points = distance_points(job.area, student.area)
    if student.experience_count > 0:
        points += 1
    if job.beginner_ok and student.experience_count == 0:
        points += 1
    return points


def rank_candidates(db: Session, job: Job) -> list[Candidate]:
    """まだ案内していない学生から、条件に合う人をスコア順に並べる。"""
    already = set(db.scalars(select(Application.student_id).where(Application.job_id == job.id)))
    candidates = [
        Candidate(s, score(s, job))
        for s in db.scalars(select(Student).order_by(Student.id))
        if s.id not in already and not exclusion_reasons(s, job)
    ]
    # スコアの高い順。同点なら id の小さい順（登録が早い順）
    candidates.sort(key=lambda c: (-c.score, c.student.id))
    return candidates
