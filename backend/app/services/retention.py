"""Enforce document TTL and record privacy-safe deletion events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select

from app.config import get_settings
from app.models import AuditEvent, DocumentRecord, get_session_factory

from .audit import add_audit_event


def delete_expired_documents(now: datetime | None = None) -> int:
    """Delete expired encrypted files, tombstone metadata, and record each event."""
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


def delete_expired_audit_events(now: datetime | None = None) -> int:
    """Remove audit rows older than the configured compliance retention window."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(
        days=get_settings().audit_retention_days
    )
    with get_session_factory()() as session:
        result = session.execute(delete(AuditEvent).where(AuditEvent.created_at < cutoff))
        session.commit()
        return result.rowcount or 0
