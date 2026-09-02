from __future__ import annotations

import chromadb

from app.services.decision_rag import (
    DecisionCardRetriever,
    DecisionRAGGate,
    DecisionRAGUnavailable,
)


class KeywordEncoder:
    model_id = "test-multilingual-e5"
    model_revision = "test"
    backend = "injected"

    def __call__(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            if (
                ("사전" in text or "일 전" in text)
                and "종료" in text
                and ("장래" in text or "변경일 이후" in text)
            ):
                vectors.append([0.0, 1.0, 0.0])
            elif any(
                term in text
                for term in (
                    "무응답",
                    "응답하지",
                    "계속 상품",
                    "계속 사용",
                    "사용하거나 보유",
                    "계속 거래",
                    "거래를 계속",
                )
            ):
                vectors.append([1.0, 0.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


def _gate() -> DecisionRAGGate:
    retriever = DecisionCardRetriever(
        encoder=KeywordEncoder(),
        client=chromadb.EphemeralClient(),
    )
    return DecisionRAGGate(retriever=retriever)


def _candidate(category: str, text: str) -> dict:
    return {
        "candidate_id": f"candidate:section:{category}",
        "category": category,
        "name": "검토 후보",
        "status": "semantic_review_candidate",
        "source": {"masked_text": text},
    }


def test_all_three_r11_patterns_are_supported_by_private_decision_rag() -> None:
    samples = (
        (
            "고객이 계속 사용하면 새 조건에 동의한 것으로 처리한다.",
            {"continued_behavior", "behavior_as_consent", "changed_terms"},
        ),
        (
            "고객이 48시간 동안 응답하지 않으면 변경 조건을 수용한 것으로 확정한다.",
            {"bounded_silence", "silence_as_consent", "choice_absent"},
        ),
        (
            "계약상 지위 이전 뒤 계속 거래하면 새 상대방을 승인한 것으로 처리한다.",
            {"continued_transaction", "assignment_context", "transaction_as_approval"},
        ),
    )
    for text, expected_factors in samples:
        assessment = _gate().assess(text, "R11_DEEMED_CONSENT")
        assert assessment.status == "supported"
        assert set(assessment.matched_factor_codes) == expected_factors


def test_decision_cards_are_versioned_synthetic_development_records() -> None:
    retriever = DecisionCardRetriever(
        encoder=KeywordEncoder(),
        client=chromadb.EphemeralClient(),
    )
    assert retriever.payload["version"] == "decision-cards-v0.1.0"
    assert all(card["source_class"] == "synthetic_development_pattern" for card in retriever.cards.values())
    assert all(card["evaluation_split"] == "development" for card in retriever.cards.values())


def test_complete_r04_safe_exception_removes_only_the_semantic_candidate() -> None:
    candidate = _candidate(
        "unilateral_change",
        "은행은 조건을 변경할 수 있다. 30일 전 개별 통지하고 고객은 변경을 거절하여 "
        "계약을 종료할 수 있으며 변경일 이후 거래에만 적용한다.",
    )
    kept, counts = _gate().filter_candidates([candidate])
    assert kept == []
    assert counts == {"supported": 0, "contested": 1, "insufficient": 0}
    assert "decision_support" not in candidate


def test_incomplete_exception_does_not_remove_a_candidate() -> None:
    candidate = _candidate(
        "unilateral_change",
        "은행은 조건을 변경할 수 있다. 30일 전 개별 통지하지만 고객은 거절할 수 없다.",
    )
    kept, counts = _gate().filter_candidates([candidate])
    assert kept == [candidate]
    assert counts["contested"] == 0


def test_unavailable_rag_preserves_existing_public_candidate() -> None:
    class UnavailableRetriever:
        def search(self, text: str, rule_id: str):
            raise DecisionRAGUnavailable("offline model missing")

    candidate = _candidate("deemed_consent", "계속 사용하면 동의한 것으로 본다.")
    kept, counts = DecisionRAGGate(retriever=UnavailableRetriever()).filter_candidates(
        [candidate]
    )
    assert kept == [candidate]
    assert counts == {"supported": 0, "contested": 0, "insufficient": 1}
