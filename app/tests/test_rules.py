from datetime import date, time

from skima.rules import (
    follow_up_question,
    high_school_blockers,
    missing_fields,
    validate_for_publish,
)
from skima.schemas import JobDraft

TODAY = date(2026, 8, 20)
MIN_WAGE = 1023


def full_draft(**overrides) -> JobDraft:
    data = dict(
        title="極早生ミカンの出荷補助",
        description="ミカン箱を軽トラックに積む",
        industry="farm",
        work_date="2026-08-23",
        start_time="07:00",
        end_time="10:00",
        headcount=2,
        hourly_wage=1100,
        area="北郷",
        location_type="land",
        max_weight_kg=10,
        items=["軍手"],
        cautions=["2人1組で運ぶ"],
    )
    data.update(overrides)
    return JobDraft(**data)


# --- 足りない項目 ---
def test_full_draft_has_no_missing():
    assert missing_fields(full_draft()) == []


def test_missing_wage_and_unknown_location():
    d = full_draft(hourly_wage=None, location_type="unknown")
    assert missing_fields(d) == ["hourly_wage", "location_type"]
    q = follow_up_question(missing_fields(d))
    assert "時給" in q and "船の上" in q


def test_no_question_when_complete():
    assert follow_up_question([]) is None


def test_unreadable_date_becomes_missing():
    d = full_draft(work_date="あした")
    assert "work_date" in missing_fields(d)


# --- 公開の判定 ---
def test_valid_draft_can_be_published():
    assert validate_for_publish(full_draft(), MIN_WAGE, TODAY) == []


def test_boat_work_is_rejected():
    codes = [e.code for e in validate_for_publish(full_draft(location_type="boat"), MIN_WAGE, TODAY)]
    assert codes == ["boat"]


def test_wage_below_minimum_is_rejected():
    codes = [e.code for e in validate_for_publish(full_draft(hourly_wage=900), MIN_WAGE, TODAY)]
    assert codes == ["min_wage"]


def test_wage_equal_to_minimum_is_ok():
    assert validate_for_publish(full_draft(hourly_wage=MIN_WAGE), MIN_WAGE, TODAY) == []


def test_end_before_start_is_rejected():
    codes = [e.code for e in validate_for_publish(full_draft(start_time="10:00", end_time="07:00"), MIN_WAGE, TODAY)]
    assert codes == ["time_order"]


def test_past_date_is_rejected():
    codes = [e.code for e in validate_for_publish(full_draft(work_date="2026-08-01"), MIN_WAGE, TODAY)]
    assert codes == ["past_date"]


# --- 高校生に表示できるか ---
def test_normal_job_is_visible_to_high_school():
    assert high_school_blockers(time(7), time(10), 10, "land") == []


def test_boundary_5_to_22_is_ok():
    assert high_school_blockers(time(5), time(22), 15, "land") == []


def test_night_work_is_hidden():
    assert "5時〜22時の範囲外" in high_school_blockers(time(20), time(23), 10, "land")
    assert "5時〜22時の範囲外" in high_school_blockers(time(4, 30), time(8), 10, "land")


def test_heavy_work_is_hidden():
    assert "15kgを超える重さ" in high_school_blockers(time(7), time(10), 16, "land")


def test_unknown_weight_is_hidden():
    # 重さが分からない作業は、安全側に倒して表示しない
    assert high_school_blockers(time(7), time(10), None, "land") != []


def test_boat_is_hidden():
    assert "陸上の作業ではない" in high_school_blockers(time(7), time(10), 10, "boat")
