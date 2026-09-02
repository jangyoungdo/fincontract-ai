from typing import Any

import pytest

from app.config import get_settings
from app.llm.provider import ProviderError
from app.services.deterministic_summary import enrich_summaries
from app.services.openai_summary import OpenAIReviewSummarizer


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _result() -> dict[str, Any]:
    return enrich_summaries(
        {
            "findings": [
                {
                    "finding_id": "finding:test",
                    "clause": {"label": "제3조"},
                    "source": {
                        "masked_text": "채권자는 금리를 변경할 수 있다.",
                        "match_span": [0, 18],
                    },
                    "rule_signal": {
                        "rule_name": "금리 변경",
                        "category": "unilateral_modification",
                        "signal_strength": "high",
                    },
                }
            ],
            "candidate_findings": [],
        }
    )


class SummaryProvider:
    name = "openai"

    @staticmethod
    def summarize_review(snapshot, model, max_tokens):
        assert snapshot["rule_finding_count"] == 1
        assert snapshot["rule_findings"][0]["section"] == "제3조"
        return {
            "lines": [
                "금리 변경 위험 신호 1건이 확인되었습니다.",
                "제3조의 변경 조건과 고객에게 미치는 영향을 우선 검토해야 합니다.",
            ]
        }

    @staticmethod
    def last_call_metadata():
        return {
            "model": "gpt-test",
            "response_id": "resp-summary",
            "prompt_version": "review-summary-v1",
            "stored": False,
        }


def test_openai_summary_replaces_only_headline_and_records_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_SUMMARY_ENABLED", "true")
    get_settings.cache_clear()
    result = _result()
    top_categories = list(result["summary"]["top_categories"])

    usage, warnings = OpenAIReviewSummarizer(SummaryProvider()).enrich(result)

    assert len(result["summary"]["lines"]) == 2
    assert result["summary"]["headline"].startswith("금리 변경")
    assert result["summary"]["top_categories"] == top_categories
    assert result["summary"]["generation"]["method"] == "openai"
    assert usage[0]["role"] == "review_summarizer"
    assert warnings == set()


def test_openai_summary_failure_preserves_deterministic_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_SUMMARY_ENABLED", "true")
    get_settings.cache_clear()
    result = _result()
    fallback = result["summary"]["headline"]
    fallback_lines = list(result["summary"]["lines"])

    class FailingProvider(SummaryProvider):
        @staticmethod
        def summarize_review(snapshot, model, max_tokens):
            raise ProviderError("LLM_UNAVAILABLE", retryable=True)

    usage, warnings = OpenAIReviewSummarizer(FailingProvider()).enrich(result)

    assert result["summary"]["headline"] == fallback
    assert result["summary"]["lines"] == fallback_lines
    assert result["summary"]["generation"]["method"] == "deterministic_fallback"
    assert usage == []
    assert warnings == {"OPENAI_SUMMARY_FAILED"}
