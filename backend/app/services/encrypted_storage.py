"""Encrypted-at-rest document storage using a deployment-provided Fernet key."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


@lru_cache
def get_fernet() -> Fernet:
    key = get_settings().document_encryption_key
    if not key:
        raise RuntimeError("DOCUMENT_ENCRYPTION_KEY is required")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("DOCUMENT_ENCRYPTION_KEY must be a valid Fernet key") from exc


def write_encrypted(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(get_fernet().encrypt(data))


def read_encrypted(path: Path) -> bytes:
    try:
        return get_fernet().decrypt(path.read_bytes())
    except InvalidToken as exc:
        raise ValueError("저장된 문서의 암호화 무결성 검증에 실패했습니다.") from exc
