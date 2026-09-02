"""Redis-backed analysis job queue and short-lived, non-sensitive progress state."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from redis import Redis

from app.config import get_settings
from app.models import AnalysisRecord, DocumentRecord, get_session_factory

from .analysis_pipeline import DocumentAnalysisPipeline
from .audit import add_audit_event
from .encrypted_storage import read_encrypted
from .source_previews import generate_pdf_source_previews
from .text_extraction import extract_document

QUEUE_NAME = "fincontract:analysis:queue"
DEAD_LETTER_QUEUE_NAME = "fincontract:analysis:dead-letter"
PROGRESS_TTL_SECONDS = 60 * 60
logger = logging.getLogger("fincontract.analysis_jobs")


def progress_key(analysis_id: str) -> str:
    """Build the short-lived progress key for one opaque analysis identifier."""
    return f"fincontract:analysis:{analysis_id}:progress"


def attempt_key(analysis_id: str) -> str:
    """Build the retry-counter key without including document content."""
    return f"fincontract:analysis:{analysis_id}:attempts"


def get_redis() -> Redis:
    """Create a decoded Redis client from runtime configuration."""
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def set_progress(redis_client: Redis, analysis_id: str, state: str, percent: int) -> None:
    """Persist non-sensitive progress for one hour to avoid indefinite tracking."""
    payload = json.dumps(
        {"state": state, "percent": percent, "updated_at": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False,
    )
    redis_client.set(progress_key(analysis_id), payload, ex=PROGRESS_TTL_SECONDS)


def get_progress(redis_client: Redis, analysis_id: str) -> dict[str, Any] | None:
    """Read the current progress snapshot when it has not expired."""
    raw = redis_client.get(progress_key(analysis_id))
    return json.loads(raw) if raw else None


def enqueue_analysis(redis_client: Redis, analysis_id: str) -> None:
    """Queue only an analysis ID; document bytes remain in encrypted storage."""
    set_progress(redis_client, analysis_id, "queued", 0)
    redis_client.rpush(QUEUE_NAME, analysis_id)


def process_analysis(analysis_id: str, redis_client: Redis | None = None) -> None:
    """Process one persisted job. The queue contains only an opaque analysis ID."""
    overall_started = time.perf_counter()
    logger.info("analysis.job.start analysis_id=%s", analysis_id)
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
            stage_started = time.perf_counter()
            data = read_encrypted(Path(document.storage_path))
            logger.info(
                "analysis.job.storage_read_done analysis_id=%s bytes=%s elapsed_ms=%.2f",
                analysis_id,
                len(data),
                (time.perf_counter() - stage_started) * 1000,
            )
            extension = Path(document.original_filename).suffix.lower()
            stage_started = time.perf_counter()
            extracted = extract_document(data, extension)
            logger.info(
                "analysis.job.extraction_done analysis_id=%s extension=%s pages=%s chars=%s elapsed_ms=%.2f",
                analysis_id,
                extension,
                len(extracted.pages),
                len(extracted.text),
                (time.perf_counter() - stage_started) * 1000,
            )
            stage_started = time.perf_counter()
            result = DocumentAnalysisPipeline().run(
                extracted.text,
                record.experiment_arm,
                pages=extracted.pages,
                source_extension=extension,
            )
            logger.info(
                "analysis.job.pipeline_done analysis_id=%s findings=%s candidates=%s elapsed_ms=%.2f",
                analysis_id,
                len(result.get("findings", [])),
                len(result.get("candidate_findings", [])),
                (time.perf_counter() - stage_started) * 1000,
            )
            if extension == ".pdf":
                stage_started = time.perf_counter()
                result = generate_pdf_source_previews(
                    data,
                    analysis_id,
                    result,
                    get_settings().report_dir,
                    get_settings(),
                    extracted.pages,
                )
                logger.info(
                    "analysis.job.previews_done analysis_id=%s elapsed_ms=%.2f",
                    analysis_id,
                    (time.perf_counter() - stage_started) * 1000,
                )
            record.status = "completed"
            record.disposition = result["disposition"]
            record.result_json = json.dumps(result, ensure_ascii=False)
            record.completed_at = datetime.now(timezone.utc)
            add_audit_event(
                session,
                "analysis_completed",
                document_id=document.id,
                analysis_id=analysis_id,
            )
            if redis_client:
                set_progress(redis_client, analysis_id, "completed", 100)
        except Exception as exc:
            # Retrying reuses the persisted analysis ID. Once the configured limit
            # is reached, the job is isolated in the DLQ and requires human review.
            attempts = 1
            if redis_client:
                attempts = int(redis_client.incr(attempt_key(analysis_id)))
                redis_client.expire(attempt_key(analysis_id), PROGRESS_TTL_SECONDS)
            retryable = getattr(exc, "retryable", True)
            # Log only exception class and stable code. Exception messages can
            # contain parser context and therefore are intentionally excluded.
            logger.warning(
                "analysis job failed analysis_id=%s exception_type=%s code=%s attempt=%s retryable=%s",
                analysis_id,
                type(exc).__name__,
                getattr(exc, "code", "ANALYSIS_FAILED"),
                attempts,
                retryable,
            )
            if redis_client and retryable and attempts < get_settings().worker_max_attempts:
                record.status = "queued"
                record.error_code = "ANALYSIS_RETRYING"
                redis_client.rpush(QUEUE_NAME, analysis_id)
                set_progress(redis_client, analysis_id, "retrying", 0)
                session.commit()
                return
            record.status = "failed"
            record.disposition = "needs_review"
            record.error_code = getattr(exc, "code", "ANALYSIS_FAILED")
            add_audit_event(
                session,
                "analysis_failed",
                document_id=document.id,
                analysis_id=analysis_id,
            )
            if redis_client:
                redis_client.rpush(DEAD_LETTER_QUEUE_NAME, analysis_id)
                set_progress(redis_client, analysis_id, "failed", 100)
        commit_started = time.perf_counter()
        session.commit()
        logger.info(
            "analysis.job.done analysis_id=%s status=%s commit_ms=%.2f total_ms=%.2f",
            analysis_id,
            record.status,
            (time.perf_counter() - commit_started) * 1000,
            (time.perf_counter() - overall_started) * 1000,
        )
