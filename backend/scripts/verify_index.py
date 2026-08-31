#!/usr/bin/env python3
from __future__ import annotations

import argparse

from app.services.retrieval import HybridRetriever
from app.vectorstore.client import COLLECTION_NAMES, ensure_collections, get_chroma_client


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="사업자가 계약 내용을 일방적으로 변경")
    args = parser.parse_args()
    assert ensure_collections() == sorted(COLLECTION_NAMES)
    counts = {name: get_chroma_client().get_collection(name).count() for name in COLLECTION_NAMES}
    results = HybridRetriever().search(args.query)
    print({"collections": counts, "result_count": len(results), "top": results[:1]})
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
