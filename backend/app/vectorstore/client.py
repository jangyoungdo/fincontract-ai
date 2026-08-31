from __future__ import annotations

from functools import lru_cache

import chromadb

from app.config import get_settings

COLLECTION_NAMES = (
    "statutes",
    "ftc_decisions",
    "court_decisions",
    "dispute_cases",
    "clause_patterns",
)


@lru_cache
def get_chroma_client():
    """Return a cached HTTP or persistent Chroma client for the configured mode."""
    settings = get_settings()
    if settings.chroma_mode == "http":
        return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    settings.chroma_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(settings.chroma_path))


def ensure_collections() -> list[str]:
    """Idempotently create the five architecture-defined legal collections."""
    client = get_chroma_client()
    for name in COLLECTION_NAMES:
        client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
    return sorted(collection.name for collection in client.list_collections())
