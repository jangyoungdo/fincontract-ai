import pytest

from app.evaluation import summarize_expert_annotations


def annotation(case_id: str, reviewer_id: str, risk_level: str, **extra) -> dict:
    """Build one content-free blinded judgment for metric tests."""
    return {
        "case_id": case_id,
        "reviewer_id": reviewer_id,
        "risk_level": risk_level,
        "evidence_ids": [],
        "reason_codes": ["SYNTHETIC_REASON"],
        "review_question_codes": [],
        "blinded": True,
        **extra,
    }


def test_expert_summary_calculates_agreement_and_preserves_disagreements() -> None:
    metrics = summarize_expert_annotations(
        [
            annotation("case-1", "reviewer-a", "high"),
            annotation("case-1", "reviewer-b", "high"),
            annotation("case-2", "reviewer-a", "low"),
            annotation("case-2", "reviewer-b", "medium"),
            annotation("case-3", "reviewer-a", "none"),
            annotation("case-3", "reviewer-b", "none"),
        ]
    )
    assert metrics["case_count"] == 3
    assert metrics["exact_agreement_rate"] == 0.666667
    assert metrics["fleiss_kappa"] == 0.538462
    assert metrics["disagreements"] == [
        {
            "case_id": "case-2",
            "ratings": {"reviewer-a": "low", "reviewer-b": "medium"},
        }
    ]


def test_expert_summary_rejects_free_text_and_identity_fields() -> None:
    with pytest.raises(ValueError, match="Unsupported expert annotation fields"):
        summarize_expert_annotations(
            [
                annotation("case-1", "reviewer-a", "high", reviewer_name="실명"),
                annotation("case-1", "reviewer-b", "high"),
            ]
        )


def test_expert_summary_requires_two_reviewers_for_every_case() -> None:
    with pytest.raises(ValueError, match="at least two"):
        summarize_expert_annotations([annotation("case-1", "reviewer-a", "high")])
