"""Evaluate a populated retrieval index against versioned relevance judgments."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.vectorstore.evaluation import evaluate


def main() -> int:
    """Load JSONL judgments, print machine-readable metrics, and enforce thresholds."""
    parser = argparse.ArgumentParser()
    parser.add_argument("cases", type=Path)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--embedding-provider")
    parser.add_argument("--min-hit-rate", type=float, default=1.0)
    parser.add_argument("--min-mrr", type=float, default=0.8)
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    metrics = evaluate(cases, args.top_k, args.embedding_provider)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    passed = metrics[f"hit@{args.top_k}"] >= args.min_hit_rate and metrics["mrr"] >= args.min_mrr
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
