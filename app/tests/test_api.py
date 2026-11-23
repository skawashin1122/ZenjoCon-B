from datetime import date, time, timedelta

from skima.applications import send_offers
from skima.config import get_settings
from skima.db import SessionLocal
from skima.models import Application, Job, Notification

from .conftest import A, B, C, D, PRODUCER, login

WAV = ("voice.wav", b"RIFF0000WAVEfake", "audio/wav")
JPG = ("photo.jpg", b"\xff\xd8\xff fake", "image/jpeg")


def publish_mock_job(client) -> int:
    """生産者としてログインし、仮AIの下書き → 時給を答える → 公開 までを行う。"""
    login(client, "producer", PRODUCER)
    job_id = client.post("/api/drafts", files={"photo": JPG, "audio": WAV}).json()["job_id"]
    client.post(f"/api/jobs/{job_id}/answer", files={"audio": WAV})
    assert client.post(f"/api/jobs/{job_id}/publish").status_code == 200
    return job_id


def make_job(headcount: int) -> int:
    """テスト用に、公開済みの求人を直接作って案内を送る。"""
    with SessionLocal() as db:
        job = Job(
            producer_id=PRODUCER, status="published", title="テスト作業", industry="farm",
            work_date=date.today() + timedelta(days=1), start_time=time(8), end_time=time(10),
            headcount=headcount, hourly_wage=1100, area="北郷", location_type="land", max_weight_kg=10,
        )
        db.add(job)
        db.flush()
        send_offers(db, get_settings(), job)
        db.commit()
        return job.id


def app_id(job_id: int, student_id: int) -> int | None:
    with SessionLocal() as db:
        a = db.query(Application).filter_by(job_id=job_id, student_id=student_id).one_or_none()
        return a.id if a else None


# ---------- 生産者：下書き → 聞き直し → 公開 ----------
def test_producer_flow_and_offers(client):
    login(client, "producer", PRODUCER)
    data = client.post("/api/drafts", files={"photo": JPG, "audio": WAV}).json()
    assert data["missing"] == ["hourly_wage"] and "時給" in data["question"]
    job_id = data["job_id"]
    assert client.post(f"/api/jobs/{job_id}/publish").status_code == 422  # 足りないまま公開はできない

    data = client.post(f"/api/jobs/{job_id}/answer", files={"audio": WAV}).json()
    assert data["can_publish"] and "時給1100円" in data["speech"]

    r = client.post(f"/api/jobs/{job_id}/publish").json()
    # 承認済みの A と D だけに案内が届く（B・C は未承認）
    assert r["offered"] == 2 and r["visible_to_high_school"]
    assert app_id(job_id, A) and app_id(job_id, D)
    assert app_id(job_id, B) is None and app_id(job_id, C) is None

    # 公開後は変更できない
    assert client.post(f"/api/jobs/{job_id}/answer", files={"audio": WAV}).status_code == 409


def test_ranking_order(client):
    job_id = make_job(headcount=1)
    with SessionLocal() as db:
        apps = db.query(Application).filter_by(job_id=job_id).order_by(Application.score.desc()).all()
    # A: 同じ地区3＋経験1＝4、D: となりの地区2＋初心者1＝3
    assert [(a.student_id, a.score) for a in apps] == [(A, 4), (D, 3)]


# ---------- 高校生：参加（先着）・定員・キャンセル ----------
def test_confirm_until_full(client):
    job_id = publish_mock_job(client)  # 定員2人
    login(client, "student", A)
    assert "お手伝いの募集" in client.get("/student").text
    assert "参加する" in client.get(f"/jobs/{job_id}").text
    assert client.post(f"/api/applications/{app_id(job_id, A)}/confirm").json()["status"] == "confirmed"
    login(client, "student", D)
    assert client.post(f"/api/applications/{app_id(job_id, D)}/confirm").json()["status"] == "confirmed"
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        assert job.status == "closed" and job.confirmed_count == 2
        # 生産者に確定の通知が2回届いている
        assert db.query(Notification).filter_by(recipient_type="producer").count() == 2
    login(client, "producer", PRODUCER)
    assert "参加 2/2人" in client.get("/producer").text


def test_no_overbooking(client):
    job_id = make_job(headcount=1)
    login(client, "student", A)
    assert client.post(f"/api/applications/{app_id(job_id, A)}/confirm").status_code == 200
    login(client, "student", D)
    r = client.post(f"/api/applications/{app_id(job_id, D)}/confirm")
    assert r.status_code == 409 and "締め切り" in r.json()["detail"]
    with SessionLocal() as db:
        assert db.get(Job, job_id).confirmed_count == 1


def test_cancel_reopens_and_offers_next(client):
    job_id = make_job(headcount=1)  # A と D に案内
    login(client, "student", A)
    client.post(f"/api/applications/{app_id(job_id, A)}/confirm")

    # 先生が B を承認しておく
    login(client, "teacher", passcode="test-pass")
    client.post(f"/api/teacher/students/{B}/checks", json={"parent_consent": True, "school_permission": True})
    assert client.post(f"/api/teacher/students/{B}/approve").json()["approved"]

    login(client, "student", A)
    assert client.post(f"/api/applications/{app_id(job_id, A)}/cancel").json()["status"] == "cancelled"
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        assert job.status == "published" and job.confirmed_count == 0
    # 空いた枠は、次の順位の B に案内される
    assert app_id(job_id, B) is not None


def test_cannot_use_others_application(client):
    job_id = make_job(headcount=2)
    login(client, "student", D)
    assert client.post(f"/api/applications/{app_id(job_id, A)}/confirm").status_code == 404


# ---------- 教員：承認 ----------
def test_teacher_needs_both_checks(client):
    login(client, "teacher", passcode="test-pass")
    assert client.post(f"/api/teacher/students/{C}/approve").status_code == 422
    client.post(f"/api/teacher/students/{C}/checks", json={"parent_consent": True, "school_permission": False})
    assert client.post(f"/api/teacher/students/{C}/approve").status_code == 422
    client.post(f"/api/teacher/students/{C}/checks", json={"parent_consent": True, "school_permission": True})
    assert client.post(f"/api/teacher/students/{C}/approve").json()["approved"] is True
    # チェックを外すと承認も取り消される
    r = client.post(f"/api/teacher/students/{C}/checks", json={"parent_consent": False, "school_permission": True})
    assert r.json()["approved"] is False


def test_wrong_passcode(client):
    r = client.post("/login", data={"role": "teacher", "passcode": "wrong"}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=1"
    assert client.get("/teacher", follow_redirects=False).headers["location"] == "/login"


# ---------- 見てよい人だけが見られる ----------
def test_access_control(client):
    assert client.post("/api/drafts", files={"audio": WAV}).status_code == 401  # ログインしていない
    job_id = make_job(headcount=1)
    login(client, "student", C)  # 未承認の C には案内が無い
    assert client.get(f"/jobs/{job_id}").status_code == 404
    assert "承認がありません" in client.get("/student").text
    assert client.post(f"/api/teacher/students/{C}/approve").status_code == 401  # 生徒は教員APIを使えない


def test_student_slots(client):
    login(client, "student", A)
    day = (date.today() + timedelta(days=20)).isoformat()
    r = client.post("/api/me/slots", json={"date": day, "start": "16:00", "end": "19:00"})
    assert {"date": day, "start": "16:00", "end": "19:00"} in r.json()["slots"]
    assert client.post("/api/me/slots", json={"date": day, "start": "19:00", "end": "16:00"}).status_code == 422
    past = (date.today() - timedelta(days=1)).isoformat()
    assert client.post("/api/me/slots", json={"date": past, "start": "06:00", "end": "08:00"}).status_code == 422


def test_requires_photo_or_voice(client):
    login(client, "producer", PRODUCER)
    assert client.post("/api/drafts").status_code == 400
    r = client.post("/api/drafts", files={"audio": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400
