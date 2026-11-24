"""画面（HTMLテンプレート）の共通設定。"""
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .auth import current_user
from .config import get_settings

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
STATIC_VERSION = "4"  # CSS・JSを変えたら数字を上げる（古いキャッシュを使わせない）


def render(request: Request, name: str, status_code: int = 200, **context):
    context.setdefault("user", current_user(request))
    context.setdefault("mock_ai", get_settings().use_mock_ai)
    context.setdefault("v", STATIC_VERSION)
    # media_type に charset を明記（LINEの中のブラウザなどでも文字化けしないように）
    return templates.TemplateResponse(request, name, context, status_code=status_code,
                                      media_type="text/html; charset=utf-8")
