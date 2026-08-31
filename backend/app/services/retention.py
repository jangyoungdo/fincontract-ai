"""Enforce document TTL and record privacy-safe deletion events."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.models import DocumentRecord, get_session_factory

from .audit import add_audit_event


def delete_expired_documents(now: datetime | None = None) -> int:
    cutoff = now or datetime.now(timezone.utc)
    deleted = 0
    with get_session_factory()() as session:
        documents = session.scalars(
            select(DocumentRecord).where(
                DocumentRecord.expires_at <= cutoff,
                DocumentRecord.deleted_at.is_(None),
            )
        ).all()
        for document in documents:
            path = Path(document.storage_path)
            if path.exists():
                path.unlink()
            document.status = "expired"
            document.masked_text = None
            document.deleted_at = cutoff
            add_audit_event(session, "document_expired", document_id=document.id)
            deleted += 1
        session.commit()
    return deleted
