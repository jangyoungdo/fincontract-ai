"""Evaluate a private document without printing or versioning its text."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.llm import get_provider
from app.prototype.pii import mask_pii
from app.rules import RuleEngine
from app.services.candidate_finder import CandidateFinder
from app.services.clause_segmenter import segment_clauses
from app.services.openai_context_review import OpenAIContextReviewer
from app.services.text_extraction import extract_text


def _metrics(counts: dict[str, int]) -> dict[str, float | int]:
    precision = (
        counts["tp"] / (counts["tp"] + counts["fp"])
        if counts["tp"] + counts["fp"]
        else 0.0
    )
    recall = counts["tp"] / (counts["tp"] + counts["fn"]) if counts["tp"] + counts["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        **counts,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Private PDF/DOCX/TXT evaluation")
    parser.add_argument("document", type=Path)
    parser.add_argument("expectations", type=Path, help="JSON ground-truth file")
    parser.add_argument("--mode", choices=("rules-only", "full"), default="full")
    parser.add_argument(
        "--openai-context",
        action="store_true",
        help="Explicitly send masked analyzable clauses to the configured OpenAI provider",
    )
    args = parser.parse_args()
    if args.openai_context and args.mode != "full":
        parser.error("--openai-context requires --mode full")

    document_bytes = args.document.read_bytes()
    text = extract_text(document_bytes, args.document.suffix.lower())
    masking = mask_pii(text)
    if not masking.passed:
        raise SystemExit("PII masking failed; no evaluation result was emitted.")
    engine = RuleEngine()
    finder = CandidateFinder(engine)
    clauses = [clause for clause in segment_clauses(masking.masked_text) if clause.analyzable]
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
            "allowed_candidates": set(item.get("allowed_candidate_categories", [])),
        }
        for item in expectation_rows
    }
    category_to_rule = {rule["category"]: rule["id"] for rule in engine.ruleset["rules"]}
    actual_by_section: dict[str, set[str]] = {}
    candidates_by_section: defaultdict[str, set[str]] = defaultdict(set)
    api_candidates_by_section: defaultdict[str, set[str]] = defaultdict(set)
    clause_key: dict[str, str] = {}
    excluded: set[tuple[str, str]] = set()

    for clause in clauses:
        matches = engine.screen(clause.text)
        actual_by_section[clause.section_id] = {match.rule_id for match in matches}
        clause_key[clause.section_id] = (
            clause.section_id if clause.section_id in expected else clause.label
        )
        excluded.update((clause.section_id, match.category) for match in matches)
        if args.mode == "full":
            matched_categories = {match.category for match in matches}
            local = {
                item["category"] for item in finder.suggest(clause.text, matched_categories)
            }
            candidates_by_section[clause.section_id].update(local)
            excluded.update((clause.section_id, category) for category in local)

    context_usage: list[dict] = []
    context_warnings: list[str] = []
    if args.openai_context:
        reviewer = OpenAIContextReviewer(get_provider(), engine)
        reviewer.settings.openai_context_review_enabled = True
        context_candidates, context_usage, warnings = reviewer.review(clauses, excluded)
        context_warnings = sorted(warnings)
        for candidate in context_candidates:
            section_id = candidate["section_id"]
            category = candidate["category"]
            candidates_by_section[section_id].add(category)
            api_candidates_by_section[section_id].add(category)

    rule_totals = {"tp": 0, "fp": 0, "fn": 0}
    candidate_totals = {"tp": 0, "fp": 0, "fn": 0}
    combined_totals = {"tp": 0, "fp": 0, "fn": 0}
    results = []
    for clause in clauses:
        key = clause_key[clause.section_id]
        wanted = expected.get(
            key,
            {
                "required": set(),
                "allowed": set(),
                "forbidden": set(),
                "candidates": set(),
                "allowed_candidates": set(),
            },
        )
        actual = actual_by_section[clause.section_id]
        semantic = candidates_by_section[clause.section_id]
        required = wanted["required"]
        unexpected = actual - required - wanted["allowed"]
        forbidden_hits = actual & wanted["forbidden"]
        missing = required - actual
        rule_totals["tp"] += len(required & actual)
        rule_totals["fp"] += len(unexpected | forbidden_hits)
        rule_totals["fn"] += len(missing)

        expected_candidates = wanted["candidates"]
        candidate_missing = expected_candidates - semantic
        candidate_unexpected = semantic - expected_candidates - wanted["allowed_candidates"]
        candidate_totals["tp"] += len(expected_candidates & semantic)
        candidate_totals["fp"] += len(candidate_unexpected)
        candidate_totals["fn"] += len(candidate_missing)

        semantic_rule_ids = {category_to_rule[item] for item in semantic if item in category_to_rule}
        combined_actual = actual | semantic_rule_ids
        combined_missing = required - combined_actual
        combined_unexpected = combined_actual - required - wanted["allowed"]
        combined_forbidden = combined_actual & wanted["forbidden"]
        combined_totals["tp"] += len(required & combined_actual)
        combined_totals["fp"] += len(combined_unexpected | combined_forbidden)
        combined_totals["fn"] += len(combined_missing)

        results.append(
            {
                "section_id": clause.section_id,
                "clause": clause.label,
                "required": sorted(required),
                "actual": sorted(actual),
                "missing": sorted(missing),
                "unexpected": sorted(unexpected),
                "forbidden_hits": sorted(forbidden_hits),
                "candidate_categories": sorted(semantic),
                "openai_candidate_categories": sorted(
                    api_candidates_by_section[clause.section_id]
                ),
                "expected_candidate_categories": sorted(expected_candidates),
                "candidate_missing": sorted(candidate_missing),
                "candidate_unexpected": sorted(candidate_unexpected),
                "combined_rule_ids": sorted(combined_actual),
                "combined_missing": sorted(combined_missing),
                "rules_passed": not missing and not unexpected and not forbidden_hits,
                "candidates_passed": not candidate_missing and not candidate_unexpected,
                "combined_passed": (
                    not combined_missing and not combined_unexpected and not combined_forbidden
                ),
            }
        )

    evaluated_rows = [
        item
        for item in results
        if item["section_id"] in expected or item["clause"] in expected
    ]
    print(
        json.dumps(
            {
                "document_sha256": hashlib.sha256(document_bytes).hexdigest(),
                "ruleset_version": engine.version,
                "evaluation_mode": args.mode,
                "semantic_model": finder.metadata if args.mode == "full" else None,
                "openai_context_enabled": args.openai_context,
                "openai_context_usage": context_usage,
                "openai_context_warnings": context_warnings,
                "pii_replacement_count": masking.replacement_count,
                "clauses": results,
                "metrics": _metrics(rule_totals),
                "candidate_metrics": _metrics(candidate_totals),
                "combined_metrics": _metrics(combined_totals),
                "passed": all(item["rules_passed"] for item in evaluated_rows),
                "combined_passed": all(item["combined_passed"] for item in evaluated_rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
