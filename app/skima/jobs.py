"""求人（Job）と下書き（JobDraft）の変換、読み上げ文の作成。"""
from datetime import date, time

from .models import Job
from .schemas import JobDraft

WEEKDAYS = "月火水木金土日"


def draft_from_job(job: Job) -> JobDraft:
    return JobDraft(
        title=job.title,
        description=job.description,
        industry=job.industry,
        work_date=job.work_date.isoformat() if job.work_date else None,
        start_time=job.start_time.strftime("%H:%M") if job.start_time else None,
        end_time=job.end_time.strftime("%H:%M") if job.end_time else None,
        headcount=job.headcount,
        hourly_wage=job.hourly_wage,
        area=job.area,
        location_type=job.location_type,
        max_weight_kg=job.max_weight_kg,
        items=list(job.items or []),
        cautions=list(job.cautions or []),
        beginner_ok=job.beginner_ok,
    )


def apply_draft(job: Job, draft: JobDraft) -> None:
    job.title = draft.title
    job.description = draft.description
    job.industry = draft.industry.value
    job.work_date = draft.parsed_date()
    job.start_time = draft.parsed_start()
    job.end_time = draft.parsed_end()
    job.headcount = draft.headcount
    job.hourly_wage = draft.hourly_wage
    job.area = draft.area
    job.location_type = draft.location_type.value
    job.max_weight_kg = draft.max_weight_kg
    job.items = list(draft.items)
    job.cautions = list(draft.cautions)
    job.beginner_ok = draft.beginner_ok


def date_text(d: date | None) -> str:
    return f"{d.month}/{d.day}（{WEEKDAYS[d.weekday()]}）" if d else "未定"


def time_text(t: time | None) -> str:
    return f"{t.hour}:{t.minute:02d}" if t else "未定"


def _spoken_time(t: time) -> str:
    return f"{t.hour}時" + (f"{t.minute}分" if t.minute else "")


def speech_text(draft: JobDraft) -> str:
    """生産者が耳で確認できるように、下書きを読み上げる文にする。"""
    parts: list[str] = []
    if draft.title:
        parts.append(draft.title + "。")
    d = draft.parsed_date()
    if d:
        parts.append(f"{d.month}月{d.day}日、{WEEKDAYS[d.weekday()]}曜日。")
    s, e = draft.parsed_start(), draft.parsed_end()
    if s and e:
        parts.append(f"{_spoken_time(s)}から{_spoken_time(e)}まで。")
    if draft.headcount:
        parts.append(f"{draft.headcount}人。")
    if draft.hourly_wage:
        parts.append(f"時給{draft.hourly_wage}円。")
    if draft.area:
        parts.append(f"場所は{draft.area}地区。")
    if draft.items:
        parts.append("持ち物は、" + "、".join(draft.items) + "。")
    if draft.cautions:
        parts.append("注意は、" + "、".join(draft.cautions) + "。")
    return "".join(parts)
