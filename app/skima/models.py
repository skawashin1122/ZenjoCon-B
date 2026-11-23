"""データベースの表（5つ）。

producers（生産者）/ students（学生）/ approvals（承認）/ jobs（求人）/ applications（応募）
"""
from datetime import date, datetime, time

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Producer(Base):
    __tablename__ = "producers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    area: Mapped[str] = mapped_column(String(20))  # 地区名まで（番地は持たない）
    line_user_id: Mapped[str | None] = mapped_column(String(64))

    jobs: Mapped[list["Job"]] = relationship(back_populates="producer")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(30))  # 画面には本名を出さない
    grade: Mapped[int] = mapped_column(Integer)  # 学年
    area: Mapped[str] = mapped_column(String(20))
    experience_count: Mapped[int] = mapped_column(Integer, default=0)
    # 空き時間: [{"date": "2026-08-23", "start": "06:00", "end": "12:00"}, ...]
    available_slots: Mapped[list] = mapped_column(JSON, default=list)
    line_user_id: Mapped[str | None] = mapped_column(String(64))

    approval: Mapped["Approval | None"] = relationship(back_populates="student", uselist=False)


class Approval(Base):
    """保護者同意 + 学校許可 がそろい、教員が承認した生徒だけが求人を受け取れる。"""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), unique=True)
    parent_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    school_permission: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(50))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)

    student: Mapped[Student] = relationship(back_populates="approval")

    @property
    def is_approved(self) -> bool:
        return self.parent_consent and self.school_permission and self.approved_at is not None


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    producer_id: Mapped[int] = mapped_column(ForeignKey("producers.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft / published / closed

    title: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str] = mapped_column(String(10), default="other")  # farm / fish / other
    work_date: Mapped[date | None] = mapped_column(Date)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    headcount: Mapped[int | None] = mapped_column(Integer)
    hourly_wage: Mapped[int | None] = mapped_column(Integer)
    area: Mapped[str | None] = mapped_column(String(20))
    location_type: Mapped[str] = mapped_column(String(10), default="unknown")  # land / boat / unknown
    max_weight_kg: Mapped[int | None] = mapped_column(Integer)
    items: Mapped[list] = mapped_column(JSON, default=list)
    cautions: Mapped[list] = mapped_column(JSON, default=list)
    beginner_ok: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)

    producer: Mapped[Producer] = relationship(back_populates="jobs")
    applications: Mapped[list["Application"]] = relationship(back_populates="job")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", "student_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    status: Mapped[str] = mapped_column(String(20), default="notified")  # notified / confirmed / cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    job: Mapped[Job] = relationship(back_populates="applications")
