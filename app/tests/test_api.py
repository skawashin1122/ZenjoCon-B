import pytest
from fastapi.testclient import TestClient

from skima.main import app

WAV = ("voice.wav", b"RIFF0000WAVEfake", "audio/wav")
JPG = ("photo.jpg", b"\xff\xd8\xff fake", "image/jpeg")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_full_flow_create_answer_publish(client):
    # ① 写真＋声 → 下書き（仮AIは時給が足りない下書きを返す）
    r = client.post("/api/drafts", files={"photo": JPG, "audio": WAV})
    assert r.status_code == 200
    data = r.json()
    assert data["missing"] == ["hourly_wage"]
    assert "時給" in data["question"]
    assert data["can_publish"] is False
    job_id = data["job_id"]

    # 足りないまま公開しようとすると断られる
    assert client.post(f"/api/jobs/{job_id}/publish").status_code == 422
    # 公開前の求人は学生には見えない
    assert client.get(f"/jobs/{job_id}").status_code == 404

    # ② 声で答える → 時給が埋まる
    r = client.post(f"/api/jobs/{job_id}/answer", files={"audio": WAV})
    data = r.json()
    assert data["draft"]["hourly_wage"] == 1100
    assert data["can_publish"] is True
    assert "時給1100円" in data["speech"]

    # ③ 公開 → 高校生に表示できる作業
    r = client.post(f"/api/jobs/{job_id}/publish")
    assert r.status_code == 200
    assert r.json()["visible_to_high_school"] is True

    # 学生向けの求人カードに統計ひとことが出る
    page = client.get(f"/jobs/{job_id}")
    assert page.status_code == 200
    assert "日南の統計ひとこと" in page.text

    # 公開後は変更できない
    assert client.post(f"/api/jobs/{job_id}/answer", files={"audio": WAV}).status_code == 409


def test_requires_photo_or_voice(client):
    assert client.post("/api/drafts").status_code == 400


def test_rejects_wrong_file_type(client):
    r = client.post("/api/drafts", files={"audio": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_producer_page_loads(client):
    r = client.get("/producer")
    assert r.status_code == 200
    assert "写真をとる" in r.text and "話して伝える" in r.text
