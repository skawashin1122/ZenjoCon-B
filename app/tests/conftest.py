import os

# テストは毎回まっさらなメモリ上のDBと、仮AIで動かす（本物のAPIキーやLINEは使わない）
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["GEMINI_API_KEY"] = ""
os.environ["LINE_CHANNEL_ACCESS_TOKEN"] = ""
os.environ["MIN_WAGE"] = "1023"
os.environ["TEACHER_PASSCODE"] = "test-pass"
os.environ["SECRET_KEY"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from skima.db import Base, SessionLocal, engine  # noqa: E402
from skima.main import app, seed  # noqa: E402

# デモデータの生徒id（seed の順番）
# A=1 北郷・経験1・承認済 / B=2 飫肥・未承認 / C=3 南郷・未承認 / D=4 飫肥・承認済
A, B, C, D = 1, 2, 3, 4
PRODUCER = 1


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    with TestClient(app) as c:
        yield c


def login(client, role, user_id=0, passcode=""):
    r = client.post("/login", data={"role": role, "user_id": user_id, "passcode": passcode}, follow_redirects=False)
    assert r.status_code == 303
    return r
