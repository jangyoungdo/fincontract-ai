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
from app.services.candidate_finder import CandidateFinder
from app.services.clause_segmenter import segment_clauses
from app.services.text_extraction import extract_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Private PDF/DOCX/TXT rule evaluation")
    parser.add_argument("document", type=Path)
    parser.add_argument("expectations", type=Path, help="JSON list: clause + expected_rule_ids")
    parser.add_argument("--mode", choices=("rules-only", "full"), default="full")
    args = parser.parse_args()

    document_bytes = args.document.read_bytes()
    text = extract_text(document_bytes, args.document.suffix.lower())
    masking = mask_pii(text)
    if not masking.passed:
        raise SystemExit("PII masking failed; no evaluation result was emitted.")
    engine = RuleEngine()
    candidates = CandidateFinder(engine)
    expectation_payload = json.loads(args.expectations.read_text(encoding="utf-8"))
    expectation_rows = (
        expectation_payload
        if isinstance(expectation_payload, list)
        else expectation_payload.get("sections", [])
    )
    expected = {
        item.get("section_id") or item["clause"]: {
            "required": set(item.get("required_rule_ids", item.get("expected_rule_ids", []))),
            "allowed": set(item.get("allowed_rule_ids", [])),
            "forbidden": set(item.get("forbidden_rule_ids", [])),
            "candidates": set(item.get("expected_candidate_categories", [])),
        }
        for item in expectation_rows
    }
    results = []
    totals = {"tp": 0, "fp": 0, "fn": 0}
    for clause in segment_clauses(masking.masked_text):
        if not clause.analyzable:
            continue
        actual = {match.rule_id for match in engine.screen(clause.text)}
        key = clause.section_id if clause.section_id in expected else clause.label
        wanted = expected.get(
            key,
            {"required": set(), "allowed": set(), "forbidden": set(), "candidates": set()},
        )
        semantic = []
        if args.mode == "full":
            matched_categories = {match.category for match in engine.screen(clause.text)}
            semantic = sorted(item["category"] for item in candidates.suggest(clause.text, matched_categories))
        required = wanted["required"]
        unexpected = actual - required - wanted["allowed"]
        forbidden_hits = actual & wanted["forbidden"]
        missing = required - actual
        totals["tp"] += len(required & actual)
        totals["fp"] += len(unexpected | forbidden_hits)
        totals["fn"] += len(missing)
        results.append(
            {
                "section_id": clause.section_id,
                "clause": clause.label,
                "required": sorted(required),
                "actual": sorted(actual),
                "missing": sorted(missing),
                "unexpected": sorted(unexpected),
                "forbidden_hits": sorted(forbidden_hits),
                "candidate_categories": semantic,
                "expected_candidate_categories": sorted(wanted["candidates"]),
                "passed": not missing and not unexpected and not forbidden_hits,
            }
        )
    precision = (
        totals["tp"] / (totals["tp"] + totals["fp"])
        if totals["tp"] + totals["fp"]
        else 0.0
    )
    recall = totals["tp"] / (totals["tp"] + totals["fn"]) if totals["tp"] + totals["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    print(json.dumps({
        "document_sha256": hashlib.sha256(document_bytes).hexdigest(),
        "ruleset_version": engine.version,
        "evaluation_mode": args.mode,
        "semantic_model": candidates.metadata if args.mode == "full" else None,
        "pii_replacement_count": masking.replacement_count,
        "clauses": results,
        "metrics": {
            **totals, "precision": round(precision, 6),
            "recall": round(recall, 6), "f1": round(f1, 6),
        },
        "passed": all(
            item["passed"] for item in results
            if item["section_id"] in expected or item["clause"] in expected
        ),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
