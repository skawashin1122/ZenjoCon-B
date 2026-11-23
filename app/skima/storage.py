"""写真・音声の一時保存（S3）。

流れ: 受け取る → S3に一時保存 → AIで解析 → すぐ削除
      消し忘れても、S3のライフサイクルルールで1日後に自動削除される（二重の安全策）。

AWSの鍵はコードにも .env にも書かない。
EC2に付けた LabInstanceProfile の一時的な認証情報を、boto3 が自動で取得する（IMDSv2）。

S3_BUCKET が空のとき（パソコンでの開発・テスト）は、app/tmp_uploads に同じ流れで保存・削除する。
"""
import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Protocol

from .config import APP_DIR, Settings

log = logging.getLogger(__name__)
PREFIX = "uploads/"  # ライフサイクルルール（1日で削除）の対象


class Storage(Protocol):
    def put(self, data: bytes, mime_type: str) -> str: ...
    def delete(self, key: str) -> None: ...


def _new_key(mime_type: str) -> str:
    ext = {"image/jpeg": "jpg", "image/png": "png", "audio/wav": "wav"}.get(mime_type, "bin")
    return f"{PREFIX}{date.today():%Y/%m/%d}/{uuid.uuid4().hex}.{ext}"


class S3Storage:
    def __init__(self, bucket: str, region: str | None):
        import boto3  # 使うときだけ読み込む

        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region or None)

    def put(self, data: bytes, mime_type: str) -> str:
        key = _new_key(mime_type)
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=mime_type,
            ServerSideEncryption="AES256",  # 保存中も暗号化
        )
        return key

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


class LocalStorage:
    """開発用：S3の代わりにフォルダに保存する（流れは同じ）。"""

    def __init__(self, root: Path):
        self.root = root

    def put(self, data: bytes, mime_type: str) -> str:
        key = _new_key(mime_type)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)

    def count(self) -> int:
        return sum(1 for p in self.root.rglob("*") if p.is_file()) if self.root.exists() else 0


_storage: Storage | None = None


def get_storage(settings: Settings) -> Storage:
    global _storage
    if _storage is None:
        if settings.s3_bucket:
            _storage = S3Storage(settings.s3_bucket, settings.aws_region)
        else:
            _storage = LocalStorage(APP_DIR / "tmp_uploads")
    return _storage


class TemporaryUploads:
    """with 文の中だけファイルを置いておき、抜けるとき（失敗しても）必ず削除する。"""

    def __init__(self, storage: Storage):
        self.storage = storage
        self.keys: list[str] = []

    def put(self, data: bytes, mime_type: str) -> str:
        key = self.storage.put(data, mime_type)
        self.keys.append(key)
        return key

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        for key in self.keys:
            try:
                self.storage.delete(key)
            except Exception as e:  # 消せなくても、ライフサイクルルールで1日後に消える
                log.warning("一時ファイルの削除に失敗（1日後に自動削除）: %s %s", key, e)
        return False
