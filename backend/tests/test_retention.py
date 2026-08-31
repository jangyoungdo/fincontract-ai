from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models import AuditEvent, DocumentRecord, get_session_factory
from app.services.encrypted_storage import write_encrypted
from app.services.retention import delete_expired_documents


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
    with get_session_factory()() as session:
        session.add(document)
        session.commit()

    assert delete_expired_documents(now) == 1
    assert not path.exists()
    with get_session_factory()() as session:
        stored = session.get(DocumentRecord, document.id)
        assert stored is not None
        assert stored.status == "expired"
        assert session.query(AuditEvent).filter_by(
            document_id=document.id, event_type="document_expired"
        ).one()
