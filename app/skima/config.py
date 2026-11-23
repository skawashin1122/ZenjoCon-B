"""設定値をまとめる場所。値は .env ファイル（または環境変数）から読み込む。

APIキーなどの秘密情報をプログラムに直接書かないための仕組み。
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# app フォルダ（どこから起動しても、.env とDBの場所がずれないようにする）
APP_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=APP_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
    database_url: str = f"sqlite:///{(APP_DIR / 'skima.db').as_posix()}"
    # 宮崎県最低賃金（円）。本番前に宮崎労働局で最新額を確認すること
    min_wage: int = 1023
    # アップロードできるファイルの最大サイズ（バイト）
    max_upload_bytes: int = 15 * 1024 * 1024

    @property
    def use_mock_ai(self) -> bool:
        """APIキーが無いときは、テスト用の仮AIで動かす。"""
        return not self.gemini_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
