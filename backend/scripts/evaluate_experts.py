#!/usr/bin/env python3
"""Summarize privacy-safe blinded expert annotations from JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.evaluation import summarize_expert_annotations


def main() -> int:
    """Validate the annotation contract and emit machine-readable agreement metrics."""
    parser = argparse.ArgumentParser()
    parser.add_argument("annotations", type=Path)
    args = parser.parse_args()
    annotations = [
        json.loads(line)
        for line in args.annotations.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(json.dumps(summarize_expert_annotations(annotations), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
