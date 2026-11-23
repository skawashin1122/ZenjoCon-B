"""ログイン状態の管理（デモ版）。

本選デモ用に、生産者・生徒はアカウントを選んでログインする。教員だけはパスコードが必要。
ログイン情報は署名付きのクッキー（セッション）に入れるので、利用者が書き換えることはできない。
本番運用では LINE ログインなどに置き換える。
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import Producer, Student

ROLES = ("producer", "student", "teacher")


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
    """画面を開いたときにログインしていなければ、ログイン画面へ移動させる。"""


def _require(role: str):
    def dep(request: Request) -> CurrentUser:
        user = current_user(request)
        if user is None or user.role != role:
            if request.url.path.startswith("/api/"):
                raise HTTPException(401, "ログインしてください")
            raise LoginRequired()
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
