from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidatedFile:
    extension: str
    mime_type: str


ALLOWED = {
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def validate_file(filename: str, content_type: str | None, data: bytes, max_bytes: int) -> ValidatedFile:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED:
        raise ValueError("지원 형식은 TXT, PDF, DOCX입니다.")
    if not data:
        raise ValueError("빈 파일은 업로드할 수 없습니다.")
    if len(data) > max_bytes:
        raise ValueError("파일 크기 제한을 초과했습니다.")

    expected = ALLOWED[extension]
    if extension == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("PDF 파일 시그니처가 올바르지 않습니다.")
    if extension == ".docx" and not data.startswith(b"PK\x03\x04"):
        raise ValueError("DOCX 파일 시그니처가 올바르지 않습니다.")
    if content_type and content_type not in {expected, "application/octet-stream"}:
        raise ValueError("파일 확장자와 MIME 형식이 일치하지 않습니다.")
    if extension == ".txt":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("TXT 파일은 UTF-8이어야 합니다.") from exc
    return ValidatedFile(extension, expected)
