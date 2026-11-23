"""安全と法令に関わる判定。

ここは AI に任せず、プログラムで毎回同じ結果になるように判定する。
（AIは間違えることがあるが、ここの判定は必ずルールどおりに動く）
"""
from dataclasses import dataclass
from datetime import date, time

from .schemas import JobDraft, LocationType

# 高校生に表示してよい作業の条件
HS_EARLIEST = time(5, 0)  # 労働基準法第61条: 18歳未満は22時〜翌5時に働けない
HS_LATEST = time(22, 0)
HS_MAX_WEIGHT_KG = 15  # 年少者労働基準規則第7条: 16〜17歳女子の継続作業の上限に合わせる

# 公開に必要な項目と、足りないときに聞き直す言葉（並び順 = 聞く順番）
REQUIRED_FIELDS: dict[str, str] = {
    "title": "作業の内容",
    "work_date": "日にち",
    "start_time": "始まる時刻",
    "end_time": "終わる時刻",
    "headcount": "人数",
    "hourly_wage": "時給",
    "area": "場所の地区",
    "max_weight_kg": "1回に持つ物の重さ（何キロくらい）",
}


@dataclass
class RuleError:
    code: str
    message: str  # 生産者に見せる・読み上げる言葉


def missing_fields(draft: JobDraft) -> list[str]:
    """公開に必要なのに、まだ分かっていない項目を返す。"""
    missing = [name for name in REQUIRED_FIELDS if getattr(draft, name) in (None, "")]
    if draft.location_type == LocationType.unknown:
        missing.append("location_type")
    return missing


def fill_rate(draft: JobDraft) -> float:
    """必要な項目のうち、すでに埋まっている割合（0〜1）。試用テストで「AIの下書きの正確さ」を測る。"""
    total = len(REQUIRED_FIELDS) + 1  # +1 は「陸上か船上か」
    return round((total - len(missing_fields(draft))) / total, 3)


def follow_up_question(missing: list[str]) -> str | None:
    """足りない項目だけを、1つの質問文にまとめる。"""
    if not missing:
        return None
    parts = [REQUIRED_FIELDS[name] for name in missing if name in REQUIRED_FIELDS]
    if "location_type" in missing:
        parts.append("作業するのは陸の上か船の上か")
    return "、".join(parts) + "を教えてください。"


def validate_for_publish(draft: JobDraft, min_wage: int, today: date | None = None) -> list[RuleError]:
    """公開してよいかを判定する。問題があればエラーのリストを返す（空なら公開OK）。"""
    errors: list[RuleError] = []
    today = today or date.today()

    if draft.location_type == LocationType.boat:
        errors.append(RuleError("boat", "船の上の作業は登録できません。陸の上の作業だけ募集できます。"))

    if draft.hourly_wage is not None and draft.hourly_wage < min_wage:
        errors.append(
            RuleError("min_wage", f"時給が宮崎県の最低賃金（{min_wage}円）より低いです。金額を言い直してください。")
        )

    start, end = draft.parsed_start(), draft.parsed_end()
    if start and end and end <= start:
        errors.append(RuleError("time_order", "終わりの時刻が、始まりの時刻より前になっています。"))

    if draft.headcount is not None and draft.headcount < 1:
        errors.append(RuleError("headcount", "人数は1人以上にしてください。"))

    work_date = draft.parsed_date()
    if work_date and work_date < today:
        errors.append(RuleError("past_date", "作業日が過ぎています。日にちを言い直してください。"))

    if draft.max_weight_kg is not None and draft.max_weight_kg < 0:
        errors.append(RuleError("weight", "重さの値が正しくありません。"))

    return errors


def high_school_blockers(
    start: time | None, end: time | None, max_weight_kg: int | None, location_type: str
) -> list[str]:
    """この求人を高校生に表示できない理由を返す（空なら表示してよい）。"""
    reasons: list[str] = []
    if location_type != LocationType.land.value:
        reasons.append("陸上の作業ではない")
    if start is None or end is None or start < HS_EARLIEST or end > HS_LATEST:
        reasons.append("5時〜22時の範囲外")
    if max_weight_kg is None or max_weight_kg > HS_MAX_WEIGHT_KG:
        reasons.append(f"{HS_MAX_WEIGHT_KG}kgを超える重さ")
    return reasons
