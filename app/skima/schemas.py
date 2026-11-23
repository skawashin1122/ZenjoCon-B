"""AI（Gemini）が返す「求人の下書き」の形。

Gemini にこの形（JSONスキーマ）を指定し、返ってきたJSONを Pydantic で型チェックする。
形が違えばエラーになるので、おかしなデータがそのまま保存されることはない。
"""
from datetime import date, time
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class LocationType(str, Enum):
    land = "land"  # 陸上（畑・倉庫・岸壁など）
    boat = "boat"  # 船の上
    unknown = "unknown"


class Industry(str, Enum):
    farm = "farm"
    fish = "fish"
    other = "other"


class JobDraft(BaseModel):
    title: str | None = Field(None, description="求人のタイトル。20文字以内。例: 極早生ミカンの出荷補助")
    description: str | None = Field(None, description="作業内容を、高校生にも分かる短い文で。60文字以内")
    industry: Industry = Field(Industry.other, description="農業ならfarm、漁業ならfish")
    work_date: str | None = Field(None, description="作業日 YYYY-MM-DD。話に出てこなければ null")
    start_time: str | None = Field(None, description="開始時刻 HH:MM（24時間制）。話に出てこなければ null")
    end_time: str | None = Field(None, description="終了時刻 HH:MM（24時間制）。話に出てこなければ null")
    headcount: int | None = Field(None, description="募集人数。話に出てこなければ null")
    hourly_wage: int | None = Field(None, description="時給（円）。話に出てこなければ null。推測しない")
    area: str | None = Field(None, description="地区名（例: 北郷、南郷、飫肥、油津、酒谷）。番地は書かない")
    location_type: LocationType = Field(
        LocationType.unknown, description="作業場所。陸上ならland、船の上ならboat、分からなければunknown"
    )
    max_weight_kg: int | None = Field(None, description="1人が1回に持つ物の重さの目安（kg）")
    items: list[str] = Field(default_factory=list, description="持ち物・服装。3〜5個")
    cautions: list[str] = Field(default_factory=list, description="安全のための注意点。2〜3個")
    beginner_ok: bool = Field(True, description="未経験でもできる作業なら true")

    # --- 文字列で受け取った日付・時刻を、プログラムで扱える形に変換する ---
    @field_validator("work_date")
    @classmethod
    def _check_date(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            date.fromisoformat(v)
        except ValueError:
            return None  # 読めない日付は「分からない」扱いにして聞き直す
        return v

    @field_validator("start_time", "end_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            return time.fromisoformat(v).strftime("%H:%M")
        except ValueError:
            return None

    def parsed_date(self) -> date | None:
        return date.fromisoformat(self.work_date) if self.work_date else None

    def parsed_start(self) -> time | None:
        return time.fromisoformat(self.start_time) if self.start_time else None

    def parsed_end(self) -> time | None:
        return time.fromisoformat(self.end_time) if self.end_time else None
