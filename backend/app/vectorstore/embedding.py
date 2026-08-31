from __future__ import annotations

import hashlib
import math
import re

from app.config import get_settings

DIMENSION = 128
SUPPORTED_PROVIDERS = ("local_hashing", "chroma_default")
TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
HANGUL_PATTERN = re.compile(r"^[가-힣]+$")


def tokenize(text: str) -> list[str]:
    """Normalize terms and add Korean n-grams to tolerate common case particles."""
    normalized = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    expanded = list(normalized)
    for token in normalized:
        if not HANGUL_PATTERN.fullmatch(token):
            continue
        # Korean spacing tokens often include particles (e.g. 책임을/책임과).
        # Character n-grams preserve useful overlap without a system tokenizer.
        for width in (2, 3):
            expanded.extend(f"ko{width}:{token[index:index + width]}" for index in range(len(token) - width + 1))
    return expanded


def embed(text: str) -> list[float]:
    """Deterministic offline hashing vector used only by the local prototype."""
    vector = [0.0] * DIMENSION
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DIMENSION
        vector[index] += -1.0 if digest[4] & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def provider_name(override: str | None = None) -> str:
    """Resolve and validate the embedding provider at the index boundary."""
    provider = override or get_settings().embedding_provider
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported embedding provider: {provider}")
    return provider


def embedding_metadata(provider: str | None = None) -> dict[str, str | int]:
    """Return provenance fields stored with every indexed evidence record."""
    resolved = provider_name(provider)
    if resolved == "chroma_default":
        return {
            "embedding_provider": resolved,
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dimension": 384,
        }
    return {
        "embedding_provider": resolved,
        "embedding_model": "sha256-ko-ngram-v2",
        "embedding_dimension": DIMENSION,
    }


def upsert_embedding(text: str, provider: str | None = None) -> dict:
    """Build Chroma upsert arguments without sending text to an external service."""
    resolved = provider_name(provider)
    return {} if resolved == "chroma_default" else {"embeddings": [embed(text)]}


def query_embedding(text: str, provider: str | None = None) -> dict:
    """Build provider-specific Chroma query arguments for one masked query."""
    resolved = provider_name(provider)
    return {"query_texts": [text]} if resolved == "chroma_default" else {"query_embeddings": [embed(text)]}
