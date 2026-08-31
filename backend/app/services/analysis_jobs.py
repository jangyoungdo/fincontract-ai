"""Redis-backed analysis job queue and short-lived, non-sensitive progress state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from redis import Redis

from app.config import get_settings
from app.models import AnalysisRecord, DocumentRecord, get_session_factory

from .analysis_pipeline import DocumentAnalysisPipeline
from .text_extraction import extract_text


QUEUE_NAME = "fincontract:analysis:queue"
DEAD_LETTER_QUEUE_NAME = "fincontract:analysis:dead-letter"
PROGRESS_TTL_SECONDS = 60 * 60


def progress_key(analysis_id: str) -> str:
    return f"fincontract:analysis:{analysis_id}:progress"


def attempt_key(analysis_id: str) -> str:
    return f"fincontract:analysis:{analysis_id}:attempts"


def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def set_progress(redis_client: Redis, analysis_id: str, state: str, percent: int) -> None:
    payload = json.dumps(
        {"state": state, "percent": percent, "updated_at": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False,
    )
    redis_client.set(progress_key(analysis_id), payload, ex=PROGRESS_TTL_SECONDS)


def get_progress(redis_client: Redis, analysis_id: str) -> dict[str, Any] | None:
    raw = redis_client.get(progress_key(analysis_id))
    return json.loads(raw) if raw else None


def enqueue_analysis(redis_client: Redis, analysis_id: str) -> None:
    set_progress(redis_client, analysis_id, "queued", 0)
    redis_client.rpush(QUEUE_NAME, analysis_id)


def process_analysis(analysis_id: str, redis_client: Redis | None = None) -> None:
    """Process one persisted job. The queue contains only an opaque analysis ID."""
    with get_session_factory()() as session:
        record = session.get(AnalysisRecord, analysis_id)
        if not record or record.status in {"completed", "deleted"}:
            return
        document = session.get(DocumentRecord, record.document_id)
        if not document or document.deleted_at:
            record.status = "failed"
            record.error_code = "DOCUMENT_NOT_FOUND"
            session.commit()
            return
        record.status = "analyzing"
        session.commit()
        if redis_client:
            set_progress(redis_client, analysis_id, "analyzing", 25)
        try:
            data = Path(document.storage_path).read_bytes()
            text = extract_text(data, Path(document.storage_path).suffix)
            result = DocumentAnalysisPipeline().run(text, record.experiment_arm)
            record.status = "completed"
            record.disposition = result["disposition"]
            record.result_json = json.dumps(result, ensure_ascii=False)
            record.completed_at = datetime.now(timezone.utc)
            if redis_client:
                set_progress(redis_client, analysis_id, "completed", 100)
        except Exception:
            attempts = 1
            if redis_client:
                attempts = int(redis_client.incr(attempt_key(analysis_id)))
                redis_client.expire(attempt_key(analysis_id), PROGRESS_TTL_SECONDS)
            if redis_client and attempts < get_settings().worker_max_attempts:
                record.status = "queued"
                record.error_code = "ANALYSIS_RETRYING"
                redis_client.rpush(QUEUE_NAME, analysis_id)
                set_progress(redis_client, analysis_id, "retrying", 0)
                session.commit()
                return
            record.status = "failed"
            record.disposition = "needs_review"
            record.error_code = "ANALYSIS_FAILED"
            if redis_client:
                redis_client.rpush(DEAD_LETTER_QUEUE_NAME, analysis_id)
                set_progress(redis_client, analysis_id, "failed", 100)
        session.commit()
