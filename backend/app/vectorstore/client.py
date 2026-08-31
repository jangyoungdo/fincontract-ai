from __future__ import annotations

from functools import lru_cache

import chromadb

from app.config import get_settings
from app.vectorstore.embedding import embedding_metadata, provider_name

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


def ensure_collections(embedding_provider: str | None = None) -> list[str]:
    """Create legal collections and reject an incompatible embedding index."""
    client = get_chroma_client()
    provider = provider_name(embedding_provider)
    expected = embedding_metadata(provider)
    for name in COLLECTION_NAMES:
        collection = client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine", **expected},
        )
        current_metadata = collection.metadata or {}
        indexed_provider = current_metadata.get("embedding_provider")
        if indexed_provider is None:
            # Upgrade indexes created before provider metadata was introduced.
            # Non-empty legacy indexes are migrated only when record provenance
            # proves that their explicit vectors use the configured provider.
            sample = collection.get(limit=1, include=["metadatas"])
            record_provider = sample["metadatas"][0].get("embedding_provider") if sample["ids"] else provider
            if record_provider == provider:
                mutable_metadata = {
                    key: value for key, value in current_metadata.items() if key != "hnsw:space"
                }
                collection.modify(metadata={**mutable_metadata, **expected})
                indexed_provider = provider
        if indexed_provider != provider:
            raise ValueError(
                f"Collection {name} uses {indexed_provider}; configure a separate CHROMA_PATH "
                f"for {provider}"
            )
    return sorted(collection.name for collection in client.list_collections())
