from datetime import datetime, timedelta, timezone

from app.llm.provider import ProviderError
from app.models import AnalysisRecord, AuditEvent, DocumentRecord, get_session_factory
from app.services.analysis_jobs import (
    DEAD_LETTER_QUEUE_NAME,
    QUEUE_NAME,
    enqueue_analysis,
    get_progress,
    process_analysis,
    progress_key,
    set_progress,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.queues: dict[str, list[str]] = {}

    def set(self, key: str, value: str, ex: int) -> None:
        assert ex > 0
        self.values[key] = value

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def rpush(self, key: str, value: str) -> None:
        self.queues.setdefault(key, []).append(value)

    def incr(self, key: str) -> int:
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    def expire(self, key: str, seconds: int) -> None:
        assert key in self.values and seconds > 0


def test_progress_state_is_non_sensitive_and_enqueue_uses_only_analysis_id() -> None:
    redis_client = FakeRedis()
    set_progress(redis_client, "analysis-123", "analyzing", 25)
    assert get_progress(redis_client, "analysis-123")["percent"] == 25
    assert progress_key("analysis-123") in redis_client.values

    enqueue_analysis(redis_client, "analysis-123")
    assert redis_client.queues[QUEUE_NAME] == ["analysis-123"]
    assert "document" not in redis_client.queues[QUEUE_NAME][0]


def test_failed_job_retries_then_moves_to_dead_letter_queue(monkeypatch) -> None:
    document_id = "retry-test-document"
    analysis_id = "retry-test-analysis"
    now = datetime.now(timezone.utc)
    with get_session_factory()() as session:
        session.add(
            DocumentRecord(
                id=document_id,
                original_filename="contract.txt",
                mime_type="text/plain",
                sha256="0" * 64,
                status="ready",
                storage_path="missing.enc",
                uploaded_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        session.add(
            AnalysisRecord(
                id=analysis_id,
                document_id=document_id,
                status="queued",
                disposition="pending",
                experiment_arm="D",
            )
        )
        session.commit()

    monkeypatch.setattr(
        "app.services.analysis_jobs.read_encrypted",
        lambda _: (_ for _ in ()).throw(ValueError("synthetic failure")),
    )
    redis_client = FakeRedis()
    for _ in range(3):
        process_analysis(analysis_id, redis_client)

    assert redis_client.queues[QUEUE_NAME] == [analysis_id, analysis_id]
    assert redis_client.queues[DEAD_LETTER_QUEUE_NAME] == [analysis_id]
    assert get_progress(redis_client, analysis_id)["state"] == "failed"
    with get_session_factory()() as session:
        record = session.get(AnalysisRecord, analysis_id)
        assert record is not None
        assert record.status == "failed"
        assert record.disposition == "needs_review"
        assert session.query(AuditEvent).filter_by(
            analysis_id=analysis_id, event_type="analysis_failed"
        ).one()


def test_non_retryable_provider_failure_moves_directly_to_dead_letter_queue(monkeypatch) -> None:
    """Avoid repeated external calls when privacy or schema validation fails."""
    document_id = "non-retryable-document"
    analysis_id = "non-retryable-analysis"
    now = datetime.now(timezone.utc)
    with get_session_factory()() as session:
        session.add(
            DocumentRecord(
                id=document_id,
                original_filename="contract.txt",
                mime_type="text/plain",
                sha256="1" * 64,
                status="ready",
                storage_path="synthetic.enc",
                uploaded_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        session.add(
            AnalysisRecord(
                id=analysis_id,
                document_id=document_id,
                status="queued",
                disposition="pending",
                experiment_arm="D",
            )
        )
        session.commit()

    class NonRetryablePipeline:
        def run(self, text: str, experiment_arm: str) -> dict:
            raise ProviderError("LLM_SCHEMA_INVALID", retryable=False)

    monkeypatch.setattr("app.services.analysis_jobs.read_encrypted", lambda _: b"synthetic text")
    monkeypatch.setattr(
        "app.services.analysis_jobs.DocumentAnalysisPipeline",
        NonRetryablePipeline,
    )
    redis_client = FakeRedis()
    process_analysis(analysis_id, redis_client)

    assert QUEUE_NAME not in redis_client.queues
    assert redis_client.queues[DEAD_LETTER_QUEUE_NAME] == [analysis_id]
    with get_session_factory()() as session:
        record = session.get(AnalysisRecord, analysis_id)
        assert record is not None
        assert record.status == "failed"
        assert record.disposition == "needs_review"
        assert record.error_code == "LLM_SCHEMA_INVALID"
