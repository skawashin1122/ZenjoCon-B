"""ログイン状態の管理（デモ版）。

本選デモ用に、生産者・生徒はアカウントを選んでログインする。教員だけはパスコードが必要。
ログイン情報は署名付きのクッキー（セッション）に入れるので、利用者が書き換えることはできない。
本番運用では LINE ログインなどに置き換える。
"""
import secrets
from dataclasses import dataclass
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Producer, Student

ROLES = ("producer", "student", "teacher")

# ログイン状態と「LINEのリンク用の通行証」に署名する秘密の文字列（空なら起動のたびに作る）
SECRET = get_settings().secret_key or secrets.token_urlsafe(32)

# ---------- LINE のリンク用の通行証 ----------
# LINE のリンクは LINE の中のブラウザで開くため、ふだんのブラウザのログイン状態が使えない。
# そこで、通知を送るときに「この生徒・この求人だけ」に使える署名付きの通行証をリンクに付ける。
# 署名があるので書き換えられず、7日で使えなくなる。
LINK_DAYS = 7
_links = URLSafeTimedSerializer(SECRET, salt="line-job-link")


def make_link_token(student_id: int, job_id: int) -> str:
    return _links.dumps({"s": student_id, "j": job_id})


def read_link_token(token: str, job_id: int) -> int | None:
    """通行証が正しく、期限内で、この求人のものなら生徒IDを返す。"""
    try:
        data = _links.loads(token, max_age=LINK_DAYS * 24 * 60 * 60)
    except BadSignature:  # 書き換え・期限切れ
        return None
    if not isinstance(data, dict) or data.get("j") != job_id or not isinstance(data.get("s"), int):
        return None
    return data["s"]


def safe_next(path: str | None) -> str | None:
    """ログイン後に戻る先。ほかのサイトへ飛ばされないよう、このサイトの中のパスだけ許す。"""
    if path and path.startswith("/") and not path.startswith("//") and "\\" not in path:
        return path
    return None


def login_url(next_path: str | None = None, error: bool = False) -> str:
    params = []
    if error:
        params.append("error=1")
    if nxt := safe_next(next_path):
        params.append(f"next={quote(nxt)}")
    return "/login" + ("?" + "&".join(params) if params else "")


@dataclass
class CurrentUser:
    role: str
    id: int
    name: str


def login(request: Request, role: str, user_id: int, name: str) -> None:
    request.session.clear()
    request.session.update({"role": role, "id": user_id, "name": name})


def logout(request: Request) -> None:
    request.session.clear()


def current_user(request: Request) -> CurrentUser | None:
    s = request.session
    if s.get("role") in ROLES and isinstance(s.get("id"), int):
        return CurrentUser(role=s["role"], id=s["id"], name=s.get("name", ""))
    return None


class LoginRequired(Exception):
    """画面を開いたときにログインしていなければ、ログイン画面へ移動させる（ログイン後は元の画面へ）。"""

    def __init__(self, next_path: str | None = None):
        self.next_path = next_path


def _require(role: str):
    def dep(request: Request) -> CurrentUser:
        user = current_user(request)
        if user is None or user.role != role:
            if request.url.path.startswith("/api/"):
                raise HTTPException(401, "ログインしてください")
            raise LoginRequired(request.url.path)
        return user

    return dep


require_producer = _require("producer")
require_student = _require("student")
require_teacher = _require("teacher")


def get_producer(user: CurrentUser = Depends(require_producer), db: Session = Depends(get_db)) -> Producer:
    producer = db.get(Producer, user.id)
    if producer is None:
        raise HTTPException(401, "ログインしてください")
    return producer


def get_student(user: CurrentUser = Depends(require_student), db: Session = Depends(get_db)) -> Student:
    student = db.get(Student, user.id)
    if student is None:
        raise HTTPException(401, "ログインしてください")
    return student
