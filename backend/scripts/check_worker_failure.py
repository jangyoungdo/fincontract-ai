#!/usr/bin/env python3
"""Inject a real Redis worker failure and verify retry and DLQ behavior."""

from __future__ import annotations

import argparse
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main() -> int:
    """Use an isolated SQLite database and Redis DB to verify terminal failure."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6379/15")
    args = parser.parse_args()

    run_id = uuid.uuid4().hex
    temp_root = Path(tempfile.mkdtemp(prefix="fincontract-worker-failure-"))
    os.environ["DATABASE_URL"] = f"sqlite:///{temp_root / 'failure.db'}"
    os.environ["REDIS_URL"] = args.redis_url
    os.environ["WORKER_MAX_ATTEMPTS"] = "3"
    os.environ.setdefault(
        "DOCUMENT_ENCRYPTION_KEY",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )

    # Imports follow environment setup so cached clients use the isolated resources.
    from redis import Redis

    from app.models import (
        AnalysisRecord,
        AuditEvent,
        DocumentRecord,
        get_engine,
        get_session_factory,
        upgrade_database,
    )
    from app.services.analysis_jobs import (
        DEAD_LETTER_QUEUE_NAME,
        QUEUE_NAME,
        attempt_key,
        get_progress,
        process_analysis,
        progress_key,
    )

    redis_client = Redis.from_url(args.redis_url, decode_responses=True)
    redis_client.ping()
    upgrade_database(get_engine())
    document_id = f"failure-document-{run_id}"
    analysis_id = f"failure-analysis-{run_id}"
    now = datetime.now(timezone.utc)
    with get_session_factory()() as session:
        session.add(
            DocumentRecord(
                id=document_id,
                original_filename="missing.txt",
                mime_type="text/plain",
                sha256="0" * 64,
                status="ready",
                storage_path=str(temp_root / "missing.txt.enc"),
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

    try:
        for _ in range(3):
            process_analysis(analysis_id, redis_client)

        assert redis_client.lrange(QUEUE_NAME, 0, -1).count(analysis_id) == 2
        assert redis_client.lrange(DEAD_LETTER_QUEUE_NAME, 0, -1).count(analysis_id) == 1
        assert get_progress(redis_client, analysis_id)["state"] == "failed"
        with get_session_factory()() as session:
            analysis = session.get(AnalysisRecord, analysis_id)
            assert analysis is not None and analysis.status == "failed"
            assert analysis.disposition == "needs_review"
            assert session.query(AuditEvent).filter_by(
                analysis_id=analysis_id,
                event_type="analysis_failed",
            ).one()
    finally:
        # Remove only records created by this run; other queue traffic is untouched.
        redis_client.lrem(QUEUE_NAME, 0, analysis_id)
        redis_client.lrem(DEAD_LETTER_QUEUE_NAME, 0, analysis_id)
        redis_client.delete(progress_key(analysis_id), attempt_key(analysis_id))

    print("redis worker failure path: retry x2 -> DLQ -> needs_review verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
