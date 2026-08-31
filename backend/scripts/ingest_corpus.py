#!/usr/bin/env python3
"""Ingest provenance-verified research records into their Chroma collections."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.vectorstore.client import COLLECTION_NAMES, ensure_collections, get_chroma_client
from app.vectorstore.embedding import SUPPORTED_PROVIDERS, embedding_metadata, upsert_embedding
from app.vectorstore.manifest import validate_manifest

REQUIRED_RECORD_FIELDS = {
    "document_id", "chunk_id", "corpus_type", "title", "authority", "source_url",
    "source_hash", "language", "section", "manifest_version", "review_status", "text",
}


def main() -> int:
    """Validate provenance, enforce stable IDs, and idempotently upsert records."""
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("records", type=Path)
    parser.add_argument("--schema", type=Path, default=Path("../research/manifest.schema.json"))
    parser.add_argument("--embedding-provider", choices=SUPPORTED_PROVIDERS)
    args = parser.parse_args()
    manifest = validate_manifest(args.manifest, args.schema)
    ensure_collections(args.embedding_provider)
    client = get_chroma_client()
    counts = {"add": 0, "update": 0, "skip": 0, "conflict": 0}

    for line in args.records.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        missing = REQUIRED_RECORD_FIELDS - record.keys()
        if missing:
            raise ValueError(f"Missing record fields: {sorted(missing)}")
        if record["corpus_type"] not in COLLECTION_NAMES:
            raise ValueError(f"Unknown corpus type: {record['corpus_type']}")
        if record["manifest_version"] != manifest["manifest_version"]:
            raise ValueError("Record and manifest versions differ")

        stable_id = f"{record['document_id']}:{record['chunk_id']}"
        collection = client.get_collection(record["corpus_type"])
        existing = collection.get(ids=[stable_id], include=["metadatas"])
        metadata = {key: value for key, value in record.items() if key != "text"}
        metadata.update(embedding_metadata(args.embedding_provider))
        metadata.setdefault("authority_weight", 0.5)
        # Stable IDs plus source hashes make repeated ingestion deterministic.
        if existing["ids"]:
            previous_hash = existing["metadatas"][0]["source_hash"]
            if previous_hash == record["source_hash"]:
                counts["skip"] += 1
                continue
            counts["update"] += 1
        else:
            counts["add"] += 1
        collection.upsert(
            ids=[stable_id],
            documents=[record["text"]],
            metadatas=[metadata],
            **upsert_embedding(record["text"], args.embedding_provider),
        )
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
