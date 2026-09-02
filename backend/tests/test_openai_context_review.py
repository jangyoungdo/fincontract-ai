from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from app.config import get_settings
from app.services.analysis_pipeline import DocumentAnalysisPipeline
from app.services.openai_context_review import OpenAIContextReviewer


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class Rules:
    ruleset: ClassVar[dict[str, Any]] = {
        "rules": [
            {
                "id": "R11_DEEMED_CONSENT",
                "name": "묵시적 동의 간주",
                "category": "deemed_consent",
                "candidate_terms": ["이의가 없으면 동의"],
                "explanation": {
                    "why_flagged": "명시적 의사표시 없이 동의를 간주할 수 있습니다.",
                    "review_points": ["거절 선택권이 있습니까?"],
                },
            },
            {
                "id": "R15_UNFAIR_COST_SHIFTING",
                "name": "부당한 비용 전가",
                "category": "unfair_cost_shifting",
                "candidate_terms": ["실제 손실과 무관한 비용"],
                "explanation": {
                    "why_flagged": "실제 발생 비용과 관계없는 부담일 수 있습니다.",
                    "review_points": ["실제 비용이 입증됩니까?"],
                },
            },
        ]
    }


class Provider:
    name = "openai"

    def review_context(self, sections, taxonomy, model, max_tokens):
        assert sections[0]["section_id"] == "article-7"
        assert {item["rule_id"] for item in taxonomy} == {
            "R11_DEEMED_CONSENT",
            "R15_UNFAIR_COST_SHIFTING",
        }
        return {
            "candidates": [
                {
                    "section_id": "article-7",
                    "rule_id": "R11_DEEMED_CONSENT",
                    "evidence_quote": "계속 사용하면 동의한 것으로 본다",
                    "rationale": "동의 간주 가능성",
                    "review_question": "거절 선택권이 있는가?",
                    "confidence": "high",
                    "counter_considerations": [],
                },
                {
                    "section_id": "article-8",
                    "rule_id": "R15_UNFAIR_COST_SHIFTING",
                    "evidence_quote": "원문에 없는 문구",
                    "rationale": "비용 전가 가능성",
                    "review_question": "비용이 입증되는가?",
                    "confidence": "medium",
                    "counter_considerations": [],
                },
            ]
        }

    @staticmethod
    def last_call_metadata():
        return {
            "model": "gpt-test",
            "response_id": "resp-test",
            "prompt_version": "context-review-v1",
            "input_tokens": 100,
            "output_tokens": 50,
            "stored": False,
        }


def test_context_review_accepts_exact_quote_and_rejects_hallucinated_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_CONTEXT_REVIEW_ENABLED", "true")
    monkeypatch.setenv("OPENAI_CONTEXT_MAX_CALLS", "1")
    get_settings.cache_clear()
    clauses = [
        SimpleNamespace(
            section_id="article-7",
            label="제7조",
            text="계속 사용하면 동의한 것으로 본다",
        ),
        SimpleNamespace(
            section_id="article-8",
            label="제8조",
            text="실제 손실과 무관하게 잔액의 9%를 부담한다",
        ),
    ]
    reviewer = OpenAIContextReviewer(Provider(), Rules())

    candidates, usage, warnings = reviewer.review(clauses, excluded=set())

    assert [item["rule_id"] for item in candidates] == ["R11_DEEMED_CONSENT"]
    assert candidates[0]["review_method"] == "openai_context"
    assert usage[0]["role"] == "context_reviewer"
    assert "OPENAI_CONTEXT_OUTPUT_REJECTED" in warnings


def test_context_review_never_duplicates_existing_section_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_CONTEXT_REVIEW_ENABLED", "true")
    monkeypatch.setenv("OPENAI_CONTEXT_MAX_CALLS", "1")
    get_settings.cache_clear()
    clause = SimpleNamespace(
        section_id="article-7",
        label="제7조",
        text="계속 사용하면 동의한 것으로 본다",
    )
    reviewer = OpenAIContextReviewer(Provider(), Rules())

    candidates, _, warnings = reviewer.review(
        [clause], excluded={("article-7", "deemed_consent")}
    )

    assert candidates == []
    assert "OPENAI_CONTEXT_OUTPUT_REJECTED" in warnings


def test_context_review_uses_at_most_one_document_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_CONTEXT_REVIEW_ENABLED", "true")
    monkeypatch.setenv("OPENAI_CONTEXT_MAX_CALLS", "3")
    monkeypatch.setenv("OPENAI_CONTEXT_MAX_CHARS_PER_CALL", "20")
    get_settings.cache_clear()
    clauses = [
        SimpleNamespace(section_id=f"article-{index}", label=f"제{index}조", text="가" * 15)
        for index in range(1, 4)
    ]
    reviewer = OpenAIContextReviewer(Provider(), Rules())

    batches, truncated = reviewer._batches(clauses)

    assert len(batches) == 1
    assert truncated is True
    assert reviewer.version_metadata["max_calls"] == 1


def test_pipeline_adds_context_candidate_without_promoting_rule_finding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("SEMANTIC_MODEL_ENABLED", "false")
    get_settings.cache_clear()
    pipeline = DocumentAnalysisPipeline()

    class Reviewer:
        enabled = True
        version_metadata: ClassVar[dict[str, str]] = {
            "provider": "openai",
            "prompt_version": "context-review-v1",
        }

        @staticmethod
        def review(clauses, excluded):
            clause = clauses[0]
            quote = "안내된 절차에 따른다"
            assert quote in clause.text
            return (
                [
                    {
                        "candidate_id": f"candidate:{clause.section_id}:openai:R18",
                        "category": "customer_rights_restriction",
                        "name": "고객 권리 제한",
                        "rule_id": "R18_CUSTOMER_RIGHTS_RESTRICTION",
                        "status": "semantic_review_candidate",
                        "review_method": "openai_context",
                        "confidence": "medium",
                        "model_id": "gpt-test",
                        "model_revision": "api-managed",
                        "matched_prototype_ids": [],
                        "review_questions": ["고객 권리가 제한되는가?"],
                        "rationale": "문맥 검토 필요",
                        "counter_considerations": [],
                        "evidence_quote": quote,
                        "section_id": clause.section_id,
                        "api_response_id": "resp-test",
                    }
                ],
                [{"role": "context_reviewer", "input_tokens": 100, "output_tokens": 40}],
                set(),
            )

    pipeline.context_reviewer = Reviewer()
    result = pipeline.run("제7조 절차\n고객은 안내된 절차에 따른다.", evaluation_mode="full")

    assert result["findings"] == []
    assert len(result["candidate_findings"]) == 1
    candidate = result["candidate_findings"][0]
    assert candidate["review_method"] == "openai_context"
    assert candidate["source"]["masked_text"] == "안내된 절차에 따른다"
    assert result["usage"]["calls"][-1]["role"] == "context_reviewer"
