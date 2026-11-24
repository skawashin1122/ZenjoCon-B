"""通知を送る。

- いつも：通知をデータベースに記録し、アプリの画面（お知らせ）に表示する
- LINEのトークンが設定されていて、相手のLINEが登録済みなら：LINEにも送る
LINEへの送信に失敗しても、アプリ内の通知は残るので、処理全体は止めない。
"""
import logging
import re

import httpx
from sqlalchemy.orm import Session

from .auth import make_link_token
from .config import Settings
from .models import Notification, Producer, Student

log = logging.getLogger(__name__)
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def notify(db: Session, settings: Settings, recipient: Student | Producer, text: str, url: str | None = None) -> Notification:
    kind = "student" if isinstance(recipient, Student) else "producer"
    n = Notification(recipient_type=kind, recipient_id=recipient.id, text=text, url=url)
    if settings.use_line and recipient.line_user_id:
        n.sent_via_line = _push_line(settings, recipient.line_user_id, text, _line_url(recipient, url))
    db.add(n)
    return n


def _line_url(recipient: Student | Producer, url: str | None) -> str | None:
    """生徒への求人のリンクには、その生徒・その求人だけに使える通行証を付ける（LINEの中のブラウザでも開けるように）。"""
    m = re.fullmatch(r"/jobs/(\d+)", url or "")
    if isinstance(recipient, Student) and m:
        return f"{url}?t={make_link_token(recipient.id, int(m.group(1)))}"
    return url


def _push_line(settings: Settings, line_user_id: str, text: str, url: str | None) -> bool:
    message = text + (f"\n{settings.base_url}{url}" if url else "")
    try:
        r = httpx.post(
            LINE_PUSH_URL,
            headers={"Authorization": f"Bearer {settings.line_channel_access_token}"},
            json={"to": line_user_id, "messages": [{"type": "text", "text": message}]},
            timeout=5,
        )
        r.raise_for_status()
        return True
    except httpx.HTTPError as e:
        log.warning("LINE送信に失敗: %s", e)
        return False
