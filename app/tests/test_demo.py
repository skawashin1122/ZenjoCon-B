"""第4週：本番デモの準備（空き時間の更新・最初の状態へ戻す）。"""
from datetime import date, timedelta

import pytest

from skima.config import get_settings
from skima.db import SessionLocal
from skima.models import Job, Student

from .conftest import A, B, login
from .test_api import publish_mock_job


def test_refresh_slots_moves_old_slots_to_today(client):
    with SessionLocal() as db:
        db.get(Student, A).available_slots = [{"date": "2020-01-01", "start": "06:00", "end": "12:00"}]
        db.commit()
    login(client, "teacher", passcode="test-pass")
    assert client.post("/api/teacher/demo/refresh-slots").json()["students"] == 4
    with SessionLocal() as db:
        slots = db.get(Student, A).available_slots
    assert slots[0]["date"] == date.today().isoformat()
    assert slots[-1]["date"] == (date.today() + timedelta(days=13)).isoformat()


def test_reset_is_blocked_without_demo_mode(client):
    login(client, "teacher", passcode="test-pass")
    assert client.post("/api/teacher/demo/reset").status_code == 403


@pytest.fixture
def demo_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_mode", True)


def test_reset_restores_starting_state(client, demo_mode):
    job_id = publish_mock_job(client)
    # 先生が B を承認、A を LINE につないでおく
    login(client, "teacher", passcode="test-pass")
    client.post(f"/api/teacher/students/{B}/checks", json={"parent_consent": True, "school_permission": True})
    client.post(f"/api/teacher/students/{B}/approve")
    with SessionLocal() as db:
        db.get(Student, A).line_user_id = "U_keep"
        db.commit()

    r = client.post("/api/teacher/demo/reset").json()
    assert r["jobs"] == 1
    with SessionLocal() as db:
        assert db.get(Job, job_id) is None
        b = db.get(Student, B)
        assert not b.approval.is_approved  # B は未承認に戻る
        assert db.get(Student, A).approval.is_approved
        assert db.get(Student, A).line_user_id == "U_keep"  # LINE のつながりは残る
    assert "デモ用に最初の状態へ戻す" in client.get("/teacher/results").text

    # 戻したあと、もう一度デモの流れが最初から動く
    publish_mock_job(client)


def test_students_cannot_reset(client, demo_mode):
    login(client, "student", A)
    assert client.post("/api/teacher/demo/reset").status_code == 401
    assert client.post("/api/teacher/demo/refresh-slots").status_code == 401
