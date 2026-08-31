"""PII-free audit events for document lifecycle and analysis operations."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.database import AuditEvent


def add_audit_event(
    session: Session,
    event_type: str,
    *,
    document_id: str | None = None,
    analysis_id: str | None = None,
) -> None:
    """Stage an audit event containing identifiers and state only, never document text."""
    session.add(
        AuditEvent(
            id=str(uuid.uuid4()),
            event_type=event_type,
            document_id=document_id,
            analysis_id=analysis_id,
        )
    )
