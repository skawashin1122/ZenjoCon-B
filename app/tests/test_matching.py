from datetime import date, time

from skima.matching import distance_points, slot_covers

DAY = date(2026, 8, 23)
SLOTS = [{"date": "2026-08-23", "start": "06:00", "end": "12:00"}]


def test_distance_points():
    assert distance_points("北郷", "北郷") == 3
    assert distance_points("北郷", "飫肥") == 2
    assert distance_points("北郷", "南郷") == 1
    assert distance_points(None, "南郷") == 1


def test_slot_covers():
    assert slot_covers(SLOTS, DAY, time(7), time(10))
    assert slot_covers(SLOTS, DAY, time(6), time(12))  # ちょうど同じでもOK
    assert not slot_covers(SLOTS, DAY, time(11), time(13))  # はみ出す
    assert not slot_covers(SLOTS, date(2026, 8, 24), time(7), time(10))  # 別の日
    assert not slot_covers([], DAY, time(7), time(10))
    assert not slot_covers([{"date": "bad"}], DAY, time(7), time(10))
