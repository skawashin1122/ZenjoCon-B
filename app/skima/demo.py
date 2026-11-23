"""デモ用の架空データと、本番デモの準備。

- seed：はじめて起動したときに、架空の生産者1人・生徒4人を作る
- refresh_slots：デモ生徒の空き時間を「今日から2週間・毎朝6〜12時」に更新（記録は消さない）
- reset_for_demo：求人・案内・通知・アンケートを消して、デモの最初の状態に戻す
  （試用テストの記録も消えるので、DEMO_MODE=true のときだけ使える）
"""
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Application, Approval, Job, Notification, Producer, Student, Survey

# 生徒（ニックネーム, 学年, 地区, 経験回数, 保護者同意, 学校許可, 承認済み）
# A：同じ地区・経験あり → 1位 ／ D：となりの地区・初心者 → 2位 ／ B・C：未承認 → 届かない
DEMO_STUDENTS = [
    ("生徒A", 2, "北郷", 1, True, True, True),
    ("生徒B", 2, "飫肥", 0, True, False, False),
    ("生徒C", 1, "南郷", 0, False, False, False),
    ("生徒D", 3, "飫肥", 0, True, True, True),
]


def demo_slots(days: int = 14) -> list[dict]:
    """今日から days 日間、毎朝6〜12時。"""
    return [
        {"date": (date.today() + timedelta(days=i)).isoformat(), "start": "06:00", "end": "12:00"} for i in range(days)
    ]


def seed(db: Session) -> None:
    if db.scalar(select(Producer).limit(1)):
        return
    db.add(Producer(name="デモ農家", area="北郷"))
    for nick, grade, area, exp, consent, permission, approved in DEMO_STUDENTS:
        s = Student(nickname=nick, grade=grade, area=area, experience_count=exp, available_slots=demo_slots())
        db.add(s)
        db.flush()
        db.add(Approval(
            student_id=s.id, parent_consent=consent, school_permission=permission,
            approved_by="デモ教員" if approved else None, approved_at=datetime.now() if approved else None,
        ))
    db.commit()


def refresh_slots(db: Session) -> int:
    """デモ生徒の空き時間を、今日から2週間に更新する。"""
    names = [d[0] for d in DEMO_STUDENTS]
    students = list(db.scalars(select(Student).where(Student.nickname.in_(names))))
    for s in students:
        s.available_slots = demo_slots()
    db.commit()
    return len(students)


def reset_for_demo(db: Session) -> dict:
    """求人・案内・通知・アンケートを消し、生徒の状態をデモの最初に戻す。LINEのつながりは残す。"""
    counts = {
        "surveys": db.execute(delete(Survey)).rowcount,
        "notifications": db.execute(delete(Notification)).rowcount,
        "applications": db.execute(delete(Application)).rowcount,
        "jobs": db.execute(delete(Job)).rowcount,
    }
    spec = {d[0]: d for d in DEMO_STUDENTS}
    for s in db.scalars(select(Student)):
        if s.nickname not in spec:
            continue
        _, grade, area, exp, consent, permission, approved = spec[s.nickname]
        s.grade, s.area, s.experience_count, s.available_slots = grade, area, exp, demo_slots()
        a = s.approval or Approval(student_id=s.id)
        a.parent_consent, a.school_permission = consent, permission
        a.approved_by = "デモ教員" if approved else None
        a.approved_at = datetime.now() if approved else None
        db.add(a)
    db.commit()
    return counts
