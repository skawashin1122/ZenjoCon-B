"""試用テストの結果をまとめる（教員の「試用結果」画面とCSV）。

発表で使う数値：
- 求人をつくるのにかかった時間（最初にボタンを押してから公開まで）
- AIの最初の下書きで埋まっていた項目の割合（＝AIの下書きの正確さ）
- 聞き直しの回数、AIの処理時間
- 充足率（募集人数に対して参加が決まった割合）
- アンケート（5段階）の平均
"""
import csv
import io
from dataclasses import dataclass
from statistics import mean, median

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Job, Survey

QUESTIONS = {
    "producer": ["求人をかんたんに出せた", "AIの下書きは正しかった", "また使いたい"],
    "student": ["安心して参加できた", "画面が分かりやすかった", "日南の農業・漁業に興味がわいた"],
}
SCALE = ["1 そう思わない", "2", "3", "4", "5 とてもそう思う"]


@dataclass
class Summary:
    published: int
    abandoned: int  # 公開されずに終わった下書き（途中でやめた・やり直した）
    create_seconds_median: float | None
    create_seconds_max: float | None
    fill_rate_mean: float | None
    followups_mean: float | None
    ai_seconds_mean: float | None
    headcount_total: int
    confirmed_total: int
    surveys: dict[str, dict]  # role → {"n": 人数, "means": [平均, ...], "comments": [...]}

    @property
    def fulfillment(self) -> float | None:
        return self.confirmed_total / self.headcount_total if self.headcount_total else None


def _avg(values, fn=mean):
    values = [v for v in values if v is not None]
    return round(fn(values), 2) if values else None


def summarize(db: Session) -> Summary:
    jobs = list(db.scalars(select(Job)))
    done = [j for j in jobs if j.status != "draft"]
    surveys: dict[str, dict] = {}
    for role in QUESTIONS:
        rows = list(db.scalars(select(Survey).where(Survey.role == role)))
        surveys[role] = {
            "n": len(rows),
            "means": [_avg([getattr(r, f"q{i}") for r in rows]) for i in (1, 2, 3)],
            "comments": [r.comment for r in rows if r.comment],
        }
    return Summary(
        published=len(done),
        abandoned=len(jobs) - len(done),
        create_seconds_median=_avg([j.create_seconds for j in done], median),
        create_seconds_max=_avg([j.create_seconds for j in done], max),
        fill_rate_mean=_avg([j.first_fill_rate for j in done]),
        followups_mean=_avg([j.followup_count for j in done]),
        ai_seconds_mean=_avg([j.ai_seconds for j in done]),
        headcount_total=sum(j.headcount or 0 for j in done),
        confirmed_total=sum(j.confirmed_count for j in done),
        surveys=surveys,
    )


def jobs_csv(db: Session) -> str:
    """表計算ソフトでグラフにできるよう、求人ごとの計測値をCSVにする。"""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["求人id", "状態", "作業", "作成秒数", "AI秒数", "最初の下書きの充足率", "聞き直し回数", "募集人数", "確定人数", "作成日時"])
    for j in db.scalars(select(Job).order_by(Job.id)):
        w.writerow([
            j.id, j.status, j.title, j.create_seconds, j.ai_seconds, j.first_fill_rate,
            j.followup_count, j.headcount, j.confirmed_count, j.created_at.strftime("%Y-%m-%d %H:%M"),
        ])
    return "﻿" + out.getvalue()  # 先頭のBOMで Excel でも文字化けしない
