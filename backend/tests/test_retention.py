from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import get_settings
from app.models import AnalysisRecord, AuditEvent, DocumentRecord, get_session_factory
from app.services.encrypted_storage import write_encrypted
from app.services.retention import delete_expired_audit_events, delete_expired_documents


def test_expired_encrypted_document_is_deleted_and_audited(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    path = tmp_path / "expired.txt.enc"
    write_encrypted(path, b"sensitive synthetic document")
    document = DocumentRecord(
        id="expired-test-document",
        original_filename="expired.txt",
        mime_type="text/plain",
        sha256="0" * 64,
        status="ready",
        storage_path=str(path),
        uploaded_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    analysis = AnalysisRecord(
        id="expired-test-analysis",
        document_id=document.id,
        status="completed",
        disposition="no_signal",
        experiment_arm="full",
    )
    preview_dir = get_settings().report_dir / "previews" / analysis.id
    preview_dir.mkdir(parents=True, exist_ok=True)
    (preview_dir / f"{'c' * 24}.png").write_bytes(b"masked preview")
    with get_session_factory()() as session:
        session.add(document)
        session.add(analysis)
        session.commit()

    assert delete_expired_documents(now) == 1
    assert not path.exists()
    assert not preview_dir.exists()
    with get_session_factory()() as session:
        stored = session.get(DocumentRecord, document.id)
        assert stored is not None
        assert stored.status == "expired"
        assert session.query(AuditEvent).filter_by(
            document_id=document.id, event_type="document_expired"
        ).one()


def test_expired_audit_events_are_deleted_without_removing_recent_events() -> None:
    now = datetime.now(timezone.utc)
    old_event = AuditEvent(
        id="old-audit-event",
        event_type="document_deleted",
        created_at=now - timedelta(days=366),
    )
    recent_event = AuditEvent(
        id="recent-audit-event",
        event_type="document_uploaded",
        created_at=now - timedelta(days=364),
    )
    with get_session_factory()() as session:
        session.add_all([old_event, recent_event])
        session.commit()

    assert delete_expired_audit_events(now) == 1
    with get_session_factory()() as session:
        assert session.get(AuditEvent, old_event.id) is None
        assert session.get(AuditEvent, recent_event.id) is not None
