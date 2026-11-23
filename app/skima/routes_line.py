"""LINE の友だちと、アプリの利用者（生徒・生産者）を結びつける。

1. アプリの画面で「LINEとつなぐ」を押す → 6けたの番号が出る（30分だけ有効）
2. LINE で スキマ日南 を友だち追加し、その番号を送る
3. Webhook で番号を受け取り、その人の LINE ID を記録 → 以後の通知が LINE にも届く

なりすまし対策：LINE から届いたデータは、チャネルシークレットで作った署名（X-Line-Signature）を
確かめてから使う。番号は推測されにくいランダムな数字で、30分で無効になる。
"""
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user
from .config import Settings, get_settings
from .db import get_db
from .models import Producer, Student

log = logging.getLogger(__name__)
router = APIRouter()
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
CODE_MINUTES = 30

WELCOME = "スキマ日南です。友だち追加ありがとうございます。\nアプリの画面に出ている6けたの番号を、このトークに送ってください。"
LINKED = "スキマ日南とつながりました。\nこれから、お手伝いの案内や参加の確定がLINEに届きます。"
BAD_CODE = "番号がちがうか、期限（30分）が切れています。アプリの画面で番号を出し直してください。"


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


def _me(request: Request, db: Session) -> Student | Producer:
    user = current_user(request)
    if user and user.role == "student" and (s := db.get(Student, user.id)):
        return s
    if user and user.role == "producer" and (p := db.get(Producer, user.id)):
        return p
    raise HTTPException(401, "ログインしてください")


def _find_by_code(db: Session, code: str) -> Student | Producer | None:
    now = datetime.now()
    for model in (Student, Producer):
        person = db.scalar(select(model).where(model.link_code == code, model.link_code_expires > now))
        if person:
            return person
    return None


@router.post("/api/me/line-code")
def issue_code(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    me = _me(request, db)
    for _ in range(10):  # ほかの人の有効な番号と重ならないようにする
        code = f"{secrets.randbelow(1_000_000):06d}"
        if _find_by_code(db, code) is None:
            break
    me.link_code = code
    me.link_code_expires = datetime.now() + timedelta(minutes=CODE_MINUTES)
    db.commit()
    return {"code": code, "minutes": CODE_MINUTES, "bot_url": settings.line_bot_url or None}


@router.post("/api/me/line-unlink")
def unlink(request: Request, db: Session = Depends(get_db)):
    me = _me(request, db)
    me.line_user_id = None
    db.commit()
    return {"linked": False}


@router.post("/line/webhook")
async def webhook(
    request: Request,
    x_line_signature: str | None = Header(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    body = await request.body()
    if not settings.line_channel_secret:
        raise HTTPException(503, "LINEの設定がありません")
    if not verify_signature(settings.line_channel_secret, body, x_line_signature):
        raise HTTPException(401, "署名が正しくありません")

    for event in json.loads(body).get("events", []):
        line_id = (event.get("source") or {}).get("userId")
        token = event.get("replyToken")
        if event.get("type") == "follow":
            _reply(settings, token, WELCOME)
        elif event.get("type") == "message" and (event.get("message") or {}).get("type") == "text" and line_id:
            text = event["message"]["text"].strip().translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            if not re.fullmatch(r"\d{6}", text):
                _reply(settings, token, WELCOME)
                continue
            person = _find_by_code(db, text)
            if person is None:
                _reply(settings, token, BAD_CODE)
                continue
            person.line_user_id = line_id
            person.link_code = None
            person.link_code_expires = None
            db.commit()
            _reply(settings, token, LINKED)
    return {"ok": True}  # LINE には必ず 200 を返す


def _reply(settings: Settings, reply_token: str | None, text: str) -> None:
    if not (reply_token and settings.line_channel_access_token):
        return
    try:
        httpx.post(
            LINE_REPLY_URL,
            headers={"Authorization": f"Bearer {settings.line_channel_access_token}"},
            json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]},
            timeout=5,
        ).raise_for_status()
    except httpx.HTTPError as e:
        log.warning("LINEの返信に失敗: %s", e)
