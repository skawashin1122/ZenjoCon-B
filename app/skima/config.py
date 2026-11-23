"""設定値をまとめる場所。値は .env ファイル（または環境変数）から読み込む。

APIキーなどの秘密情報をプログラムに直接書かないための仕組み。
"""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# app フォルダ（どこから起動しても、.env とDBの場所がずれないようにする）
APP_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=APP_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = ""
    # 2026-11-23 に日南弁の文で比較：3.5-flash-lite は約2秒・正確。混雑時は 3.5-flash に切り替える
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_fallback_model: str = "gemini-3.5-flash"
    database_url: str = f"sqlite:///{(APP_DIR / 'skima.db').as_posix()}"

    @field_validator("database_url")
    @classmethod
    def _sqlite_relative_to_app(cls, v: str) -> str:
        """sqlite:///./xxx.db のような相対パスは、起動した場所ではなく app フォルダを基準にする。"""
        prefix = "sqlite:///./"
        if v.startswith(prefix):
            return f"sqlite:///{(APP_DIR / v[len(prefix):]).as_posix()}"
        return v
    # 宮崎県最低賃金（円）。本番前に宮崎労働局で最新額を確認すること
    min_wage: int = 1023
    # アップロードできるファイルの最大サイズ（バイト）
    max_upload_bytes: int = 15 * 1024 * 1024

    # ログイン状態（セッション）に署名するための秘密の文字列。空なら起動のたびに作り直す
    secret_key: str = ""
    # 教員画面に入るためのパスコード。EC2では必ず変更する
    teacher_passcode: str = "demo-teacher"

    # LINE Messaging API（空なら LINE には送らず、アプリ内の通知だけ）
    line_channel_access_token: str = ""
    # 通知に載せるリンクの先頭（例: https://skima.example.jp）
    base_url: str = "http://localhost:8000"

    @property
    def use_line(self) -> bool:
        return bool(self.line_channel_access_token)

    @property
    def use_mock_ai(self) -> bool:
        """APIキーが無いときは、テスト用の仮AIで動かす。"""
        return not self.gemini_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
