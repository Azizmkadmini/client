"""Upload médias — Cloudflare R2 (S3 API) ou disque local."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from config import settings


def r2_configured() -> bool:
    return bool(
        getattr(settings, "r2_access_key_id", "")
        and getattr(settings, "r2_secret_access_key", "")
        and getattr(settings, "r2_bucket", "")
    )


def upload_bytes(data: bytes, *, mime_type: str, filename: str | None = None) -> dict[str, Any]:
    name = filename or f"{uuid.uuid4().hex}"
    if r2_configured():
        return _upload_r2(data, name=name, mime_type=mime_type)
    return _upload_local(data, name=name, mime_type=mime_type)


def _upload_local(data: bytes, *, name: str, mime_type: str) -> dict[str, Any]:
    from content.media.storage import save_media_local

    ext = ".png" if "png" in mime_type else ".jpg" if "jpeg" in mime_type else ".bin"
    return save_media_local(data, mime_type=mime_type, draft_id=None)


def _upload_r2(data: bytes, *, name: str, mime_type: str) -> dict[str, Any]:
    import boto3
    from botocore.config import Config

    account = getattr(settings, "r2_account_id", "")
    endpoint = f"https://{account}.r2.cloudflarestorage.com"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
    )
    key = f"media/{name}"
    client.put_object(
        Bucket=settings.r2_bucket,
        Key=key,
        Body=data,
        ContentType=mime_type,
    )
    base = (getattr(settings, "r2_public_base_url", "") or "").rstrip("/")
    url = f"{base}/{key}" if base else key
    return {"r2_key": key, "url": url, "storage": "r2"}
