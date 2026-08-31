#!/usr/bin/env python3
"""Verify live database, vector-store, and optional Redis read/write paths."""
from __future__ import annotations

from redis import Redis
from sqlalchemy import text

from app.config import get_settings
from app.models import get_engine, upgrade_database
from app.vectorstore.client import COLLECTION_NAMES, ensure_collections, get_chroma_client


def main() -> int:
    """Run reversible smoke writes against every configured infrastructure service."""
    settings = get_settings()
    engine = get_engine()
    assert upgrade_database(engine) in {"upgraded", "already_current"}
    with engine.begin() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
    print("database: read/write connection ready")

    collections = ensure_collections()
    assert collections == sorted(COLLECTION_NAMES)
    smoke = get_chroma_client().get_collection("clause_patterns")
    smoke.upsert(
        ids=["infra-smoke"],
        documents=["인프라 연결 검증용 합성 문장"],
        embeddings=[[0.0] * 127 + [1.0]],
        metadatas=[{"corpus_type": "clause_patterns", "synthetic": True}],
    )
    assert smoke.get(ids=["infra-smoke"])["ids"] == ["infra-smoke"]
    smoke.delete(ids=["infra-smoke"])
    print("chroma: 5 collections and read/write ready")

    if settings.use_redis:
        redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        redis_client.set("fincontract:infra-smoke", "ready", ex=10)
        assert redis_client.get("fincontract:infra-smoke") == "ready"
        redis_client.delete("fincontract:infra-smoke")
        print("redis: read/write ready")
    else:
        print("redis: disabled by configuration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
