"""Evaluate a local, non-versioned document without printing its text."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.prototype.pii import mask_pii
from app.rules import RuleEngine
from app.services.clause_segmenter import segment_clauses
from app.services.text_extraction import extract_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Private PDF/DOCX/TXT rule evaluation")
    parser.add_argument("document", type=Path)
    parser.add_argument("expectations", type=Path, help="JSON list: clause + expected_rule_ids")
    args = parser.parse_args()

    document_bytes = args.document.read_bytes()
    text = extract_text(document_bytes, args.document.suffix.lower())
    masking = mask_pii(text)
    if not masking.passed:
        raise SystemExit("PII masking failed; no evaluation result was emitted.")
    engine = RuleEngine()
    expected = {
        item["clause"]: set(item["expected_rule_ids"])
        for item in json.loads(args.expectations.read_text(encoding="utf-8"))
    }
    results = []
    for clause in segment_clauses(masking.masked_text):
        actual = {match.rule_id for match in engine.screen(clause.text)}
        wanted = expected.get(clause.label, set())
        results.append({"clause": clause.label, "expected": sorted(wanted), "actual": sorted(actual), "passed": actual == wanted})
    print(json.dumps({
        "document_sha256": hashlib.sha256(document_bytes).hexdigest(),
        "ruleset_version": engine.version,
        "pii_replacement_count": masking.replacement_count,
        "clauses": results,
        "passed": all(item["passed"] for item in results if item["clause"] in expected),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
