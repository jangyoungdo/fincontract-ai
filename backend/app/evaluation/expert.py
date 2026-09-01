"""Validate blinded expert annotations and calculate inter-rater agreement."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

RISK_LEVELS = ("none", "low", "medium", "high")
ALLOWED_FIELDS = {
    "case_id",
    "reviewer_id",
    "risk_level",
    "evidence_ids",
    "reason_codes",
    "review_question_codes",
    "blinded",
}


def _validate_annotation(annotation: dict[str, Any]) -> None:
    """Reject free text, identity fields, and incomplete blinded judgments."""
    unknown = set(annotation) - ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"Unsupported expert annotation fields: {sorted(unknown)}")
    for field in ("case_id", "reviewer_id", "risk_level"):
        if not isinstance(annotation.get(field), str) or not annotation[field].strip():
            raise ValueError(f"Expert annotation requires non-empty {field}")
    if annotation["risk_level"] not in RISK_LEVELS:
        raise ValueError(f"Unknown expert risk level: {annotation['risk_level']}")
    if annotation.get("blinded") is not True:
        raise ValueError("Expert annotation must explicitly set blinded=true")
    for field in ("evidence_ids", "reason_codes", "review_question_codes"):
        values = annotation.get(field)
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise ValueError(f"Expert annotation requires a string list for {field}")


def summarize_expert_annotations(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Return Fleiss kappa, exact agreement, and non-content disagreement details."""
    if not annotations:
        raise ValueError("Expert annotations are empty")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_pairs: set[tuple[str, str]] = set()
    for annotation in annotations:
        _validate_annotation(annotation)
        pair = (annotation["case_id"], annotation["reviewer_id"])
        if pair in seen_pairs:
            raise ValueError(f"Duplicate expert annotation: {pair[0]} / {pair[1]}")
        seen_pairs.add(pair)
        grouped[annotation["case_id"]].append(annotation)

    reviewer_counts = {len(items) for items in grouped.values()}
    if len(reviewer_counts) != 1:
        raise ValueError("Every case must have the same number of reviewer judgments")
    reviewer_count = reviewer_counts.pop()
    if reviewer_count < 2:
        raise ValueError("Every case requires at least two independent reviewers")

    case_agreements: list[float] = []
    category_totals: Counter[str] = Counter()
    disagreements = []
    for case_id, items in sorted(grouped.items()):
        counts = Counter(item["risk_level"] for item in items)
        category_totals.update(counts)
        agreeing_pairs = sum(count * (count - 1) for count in counts.values())
        case_agreements.append(agreeing_pairs / (reviewer_count * (reviewer_count - 1)))
        if len(counts) > 1:
            disagreements.append(
                {
                    "case_id": case_id,
                    "ratings": {
                        item["reviewer_id"]: item["risk_level"]
                        for item in sorted(items, key=lambda item: item["reviewer_id"])
                    },
                }
            )

    observed_agreement = sum(case_agreements) / len(case_agreements)
    rating_count = len(annotations)
    expected_agreement = sum(
        (category_totals[level] / rating_count) ** 2 for level in RISK_LEVELS
    )
    if expected_agreement == 1:
        fleiss_kappa = 1.0
    else:
        fleiss_kappa = (observed_agreement - expected_agreement) / (1 - expected_agreement)
    exact_agreement_count = sum(
        len({item["risk_level"] for item in items}) == 1 for items in grouped.values()
    )
    return {
        "case_count": len(grouped),
        "reviewer_count_per_case": reviewer_count,
        "annotation_count": rating_count,
        "exact_agreement_rate": round(exact_agreement_count / len(grouped), 6),
        "observed_pair_agreement": round(observed_agreement, 6),
        "expected_pair_agreement": round(expected_agreement, 6),
        "fleiss_kappa": round(fleiss_kappa, 6),
        "risk_level_counts": {level: category_totals[level] for level in RISK_LEVELS},
        "disagreements": disagreements,
    }
