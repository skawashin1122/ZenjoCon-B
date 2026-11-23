"""第3週：一時保存の削除・計測・アンケート・試用結果・LINE連携。"""
import base64
import hashlib
import hmac
import json

import pytest

from skima import ai
from skima.config import get_settings
from skima.db import SessionLocal
from skima.models import Job, Student
from skima.storage import LocalStorage, TemporaryUploads, get_storage

from .conftest import A, C, PRODUCER, login
from .test_api import JPG, WAV, app_id, make_job, publish_mock_job


# ---------- S3（一時保存）：解析後に必ず消える ----------
def test_uploads_are_deleted_after_analysis(client):
    storage = get_storage(get_settings())
    assert isinstance(storage, LocalStorage)  # テストでは S3 の代わりにフォルダ
    login(client, "producer", PRODUCER)
    client.post("/api/drafts", files={"photo": JPG, "audio": WAV})
    assert storage.count() == 0


def test_uploads_are_deleted_even_if_ai_fails(client, monkeypatch):
    storage = get_storage(get_settings())

    def boom(*args, **kwargs):
        raise ai.AIError("失敗")

    monkeypatch.setattr(ai, "generate_draft", boom)
    login(client, "producer", PRODUCER)
    r = client.post("/api/drafts", files={"photo": JPG, "audio": WAV})
    assert r.status_code == 502
    assert storage.count() == 0


def test_temporary_uploads_cleans_up(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(RuntimeError):
        with TemporaryUploads(storage) as tmp:
            tmp.put(b"x", "image/jpeg")
            assert storage.count() == 1
            raise RuntimeError("途中で失敗")
    assert storage.count() == 0


# ---------- 計測 ----------
def test_metrics_are_recorded(client):
    login(client, "producer", PRODUCER)
    job_id = client.post("/api/drafts", files={"audio": WAV}).json()["job_id"]
    client.post(f"/api/jobs/{job_id}/answer", files={"audio": WAV})
    client.post(f"/api/jobs/{job_id}/publish", data={"client_seconds": "42.5"})
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        assert job.create_seconds == 42.5
        assert job.followup_count == 1
        assert job.first_fill_rate == pytest.approx(8 / 9, abs=0.001)  # 9項目中、時給だけ足りなかった
        assert job.ai_first_draft["hourly_wage"] is None
        assert job.ai_seconds is not None


def test_bad_client_seconds_falls_back(client):
    login(client, "producer", PRODUCER)
    job_id = client.post("/api/drafts", files={"audio": WAV}).json()["job_id"]
    client.post(f"/api/jobs/{job_id}/answer", files={"audio": WAV})
    client.post(f"/api/jobs/{job_id}/publish", data={"client_seconds": "-5"})
    with SessionLocal() as db:
        assert db.get(Job, job_id).create_seconds >= 0


# ---------- アンケートと試用結果 ----------
def test_survey_permissions_and_results(client):
    job_id = publish_mock_job(client)
    # 生産者は自分の求人に答えられる
    assert client.get(f"/survey/{job_id}").status_code == 200
    assert client.post(f"/api/survey/{job_id}", json={"q1": 5, "q2": 4, "q3": 5, "comment": "かんたん"}).status_code == 200
    # 範囲外の値は受け付けない
    assert client.post(f"/api/survey/{job_id}", json={"q1": 6, "q2": 4, "q3": 5}).status_code == 422

    # 参加が決まっていない生徒は答えられない
    login(client, "student", A)
    assert client.post(f"/api/survey/{job_id}", json={"q1": 5, "q2": 5, "q3": 5}).status_code == 404
    client.post(f"/api/applications/{app_id(job_id, A)}/confirm")
    assert client.post(f"/api/survey/{job_id}", json={"q1": 4, "q2": 4, "q3": 3}).status_code == 200

    login(client, "teacher", passcode="test-pass")
    page = client.get("/teacher/results").text
    assert "公開した求人" in page and "1件" in page
    assert "5.0 / 5" in page and "かんたん" in page
    csv = client.get("/teacher/results.csv")
    assert csv.status_code == 200 and "作成秒数" in csv.text

    login(client, "student", A)
    assert client.get("/teacher/results", follow_redirects=False).status_code == 303  # 生徒は見られない


# ---------- LINE ----------
SECRET = "line-test-secret"


def _sign(body: bytes) -> str:
    return base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()


def _event(text: str, user: str = "U_test_line_user") -> bytes:
    return json.dumps({"events": [{
        "type": "message", "replyToken": "r", "source": {"userId": user},
        "message": {"type": "text", "text": text},
    }]}).encode()


@pytest.fixture
def line_secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "line_channel_secret", SECRET)


def test_line_webhook_rejects_bad_signature(client, line_secret):
    body = _event("123456")
    assert client.post("/line/webhook", content=body, headers={"X-Line-Signature": "wrong"}).status_code == 401
    assert client.post("/line/webhook", content=body).status_code == 401


def test_line_link_with_code(client, line_secret):
    login(client, "student", A)
    code = client.post("/api/me/line-code").json()["code"]
    assert len(code) == 6

    # 違う番号では結びつかない
    body = _event("000000" if code != "000000" else "111111")
    assert client.post("/line/webhook", content=body, headers={"X-Line-Signature": _sign(body)}).status_code == 200
    with SessionLocal() as db:
        assert db.get(Student, A).line_user_id is None

    # 正しい番号（全角でもOK）で結びつく
    zen = code.translate(str.maketrans("0123456789", "０１２３４５６７８９"))
    body = _event(zen)
    assert client.post("/line/webhook", content=body, headers={"X-Line-Signature": _sign(body)}).status_code == 200
    with SessionLocal() as db:
        s = db.get(Student, A)
        assert s.line_user_id == "U_test_line_user" and s.link_code is None
    assert "LINEとつながっています" in client.get("/student").text

    # 同じ番号は2回使えない
    body = _event(code, user="U_other")
    client.post("/line/webhook", content=body, headers={"X-Line-Signature": _sign(body)})
    with SessionLocal() as db:
        assert db.get(Student, A).line_user_id == "U_test_line_user"

    client.post("/api/me/line-unlink")
    with SessionLocal() as db:
        assert db.get(Student, A).line_user_id is None


def test_line_code_requires_login(client):
    assert client.post("/api/me/line-code").status_code == 401
    login(client, "teacher", passcode="test-pass")
    assert client.post("/api/me/line-code").status_code == 401  # 教員は対象外


def test_unapproved_student_cannot_survey(client):
    job_id = make_job(headcount=1)
    login(client, "student", C)
    assert client.get(f"/survey/{job_id}").status_code == 404
