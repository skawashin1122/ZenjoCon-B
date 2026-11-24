"""LINE のリンク（通行証付き）・ログイン後に元の画面へ戻る・日本語のエラー画面。"""
from skima.auth import make_link_token
from skima.db import SessionLocal
from skima.models import Student
from skima.notify import _line_url

from .conftest import A, C, D, login
from .test_api import make_job


def _me(client) -> str:
    return client.get("/student", follow_redirects=False).text


def test_line_link_logs_in_as_that_student(client):
    job_id = make_job(headcount=1)  # A と D に案内
    r = client.get(f"/jobs/{job_id}?t={make_link_token(A, job_id)}", follow_redirects=False)
    # 通行証を消したURLへ移動し直す
    assert r.status_code == 303 and r.headers["location"] == f"/jobs/{job_id}"
    page = client.get(f"/jobs/{job_id}")
    assert page.status_code == 200 and "参加する" in page.text
    assert "生徒A" in page.text  # 生徒Aとしてログインしている


def test_token_for_other_job_does_not_log_in(client):
    job_id = make_job(headcount=1)
    r = client.get(f"/jobs/{job_id}?t={make_link_token(A, job_id + 99)}", follow_redirects=False)
    assert r.status_code == 303
    # ログインしていないので、ログイン画面（戻り先付き）へ
    r = client.get(f"/jobs/{job_id}", follow_redirects=False)
    assert r.headers["location"] == f"/login?next=/jobs/{job_id}"


def test_tampered_token_is_ignored(client):
    job_id = make_job(headcount=1)
    token = make_link_token(A, job_id)
    bad = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    client.get(f"/jobs/{job_id}?t={bad}", follow_redirects=False)
    assert client.get(f"/jobs/{job_id}", follow_redirects=False).status_code == 303  # ログインしていない


def test_token_for_student_without_offer_does_not_log_in(client):
    job_id = make_job(headcount=1)  # 未承認の C には案内していない
    client.get(f"/jobs/{job_id}?t={make_link_token(C, job_id)}", follow_redirects=False)
    assert client.get(f"/jobs/{job_id}", follow_redirects=False).status_code == 303


def test_login_returns_to_next_page(client):
    job_id = make_job(headcount=1)
    page = client.get(f"/login?next=/jobs/{job_id}").text
    assert f'name="next" value="/jobs/{job_id}"' in page
    r = client.post("/login", data={"role": "student", "user_id": D, "next": f"/jobs/{job_id}"}, follow_redirects=False)
    assert r.headers["location"] == f"/jobs/{job_id}"


def test_next_cannot_point_outside(client):
    r = client.post("/login", data={"role": "student", "user_id": A, "next": "//evil.example.com/x"}, follow_redirects=False)
    assert r.headers["location"] == "/student"
    r = client.post("/login", data={"role": "student", "user_id": A, "next": "https://evil.example.com"}, follow_redirects=False)
    assert r.headers["location"] == "/student"


def test_wrong_passcode_keeps_next(client):
    r = client.post("/login", data={"role": "teacher", "passcode": "x", "next": "/teacher"}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=1&next=/teacher"


def test_html_error_page_has_charset(client):
    login(client, "student", A)
    r = client.get("/jobs/99999")
    assert r.status_code == 404
    assert r.headers["content-type"] == "text/html; charset=utf-8"
    assert "求人が見つかりません" in r.text


def test_api_errors_stay_json(client):
    r = client.post("/api/applications/1/confirm")
    assert r.status_code == 401 and r.json()["detail"] == "ログインしてください"


def test_line_url_gets_token_only_for_students(client):
    with SessionLocal() as db:
        a = db.get(Student, A)
        url = _line_url(a, "/jobs/7")
    assert url.startswith("/jobs/7?t=")
    assert _line_url(a, None) is None
    assert _line_url(a, "/student") == "/student"
