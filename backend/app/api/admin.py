from __future__ import annotations

import secrets

from fastapi import APIRouter, Header, HTTPException, Query, status
from sqlalchemy import desc, select

from app.config import get_settings
from app.models import AuditEvent, get_session_factory
from app.models.schemas import AuditEventResponse

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _require_admin_token(token: str | None) -> None:
    expected = get_settings().admin_audit_token
    if not expected or not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증이 필요합니다.")


@router.get("/audit-events", response_model=list[AuditEventResponse])
def list_audit_events(
    limit: int = Query(default=100, ge=1, le=200),
    document_id: str | None = None,
    x_admin_token: str | None = Header(default=None),
) -> list[AuditEventResponse]:
    """Return recent PII-free lifecycle events after constant-time token validation."""
    _require_admin_token(x_admin_token)
    query = select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(limit)
    if document_id:
        query = query.where(AuditEvent.document_id == document_id)
    with get_session_factory()() as session:
        events = session.scalars(query).all()
        return [AuditEventResponse.model_validate(event, from_attributes=True) for event in events]
