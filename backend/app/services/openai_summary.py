"""Optional OpenAI headline generation with a deterministic safe fallback."""

from __future__ import annotations

import re
from typing import Any

from app.config import get_settings
from app.llm.provider import ProviderError, REVIEW_SUMMARY_PROMPT_VERSION

FORBIDDEN_CONCLUSIONS = (
    "위법하다",
    "적법하다",
    "무효이다",
    "불공정하다",
    "법률 위반이다",
    "반드시 승소",
)
MAX_LINE_LENGTH = 100


class OpenAIReviewSummarizer:
    """Replace only the headline while preserving deterministic summaries as fallback."""

    def __init__(self, provider: Any) -> None:
        self.provider = provider
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.openai_summary_enabled
            and self.provider.name == "openai"
            and hasattr(self.provider, "summarize_review")
        )

    @property
    def version_metadata(self) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        return {
            "provider": "openai",
            "model": self.settings.openai_balanced_model,
            "prompt_version": REVIEW_SUMMARY_PROMPT_VERSION,
            "max_calls": 1,
        }

    def enrich(self, result: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
        """Generate one headline, or retain the deterministic headline on any failure."""
        summary = result.setdefault("summary", {})
        summary["generation"] = {
            "method": "deterministic_fallback",
            "prompt_version": REVIEW_SUMMARY_PROMPT_VERSION,
        }
        if not self.enabled:
            return [], set()

        try:
            output = self.provider.summarize_review(
                self._snapshot(result),
                self.settings.openai_balanced_model,
                max_tokens=320,
            )
            raw_lines = output.get("lines", [])
            lines = [re.sub(r"\s+", " ", str(line)).strip() for line in raw_lines]
            if (
                not 2 <= len(lines) <= 3
                or any(not line or len(line) > MAX_LINE_LENGTH for line in lines)
                or any(term in line for line in lines for term in FORBIDDEN_CONCLUSIONS)
            ):
                raise ValueError("unsafe summary output")
        except ProviderError as exc:
            return [], {"OPENAI_SUMMARY_FAILED"}
        except Exception:  # noqa: BLE001 - summary failure must preserve analysis output
            return [], {"OPENAI_SUMMARY_FAILED"}

        metadata = self.provider.last_call_metadata()
        summary["lines"] = lines
        summary["headline"] = " ".join(lines)
        summary["generation"] = {
            "method": "openai",
            "model": metadata.get("model", self.settings.openai_balanced_model),
            "prompt_version": REVIEW_SUMMARY_PROMPT_VERSION,
            "response_id": metadata.get("response_id"),
        }
        return [{"role": "review_summarizer", "sequence": 1, **metadata}], set()

    @staticmethod
    def _snapshot(result: dict[str, Any]) -> dict[str, Any]:
        findings = result.get("findings", [])
        candidates = result.get("candidate_findings", [])
        return {
            "rule_finding_count": len(findings),
            "candidate_finding_count": len(candidates),
            "top_categories": list(result.get("summary", {}).get("top_categories", [])),
            "rule_findings": [
                {
                    "section": item.get("clause", {}).get("label"),
                    "category": item.get("rule_signal", {}).get("rule_name"),
                    "summary": item.get("summary_sentence"),
                }
                for item in findings
            ],
            "review_candidates": [
                {
                    "section": item.get("clause", {}).get("label"),
                    "category": item.get("name") or item.get("category"),
                    "summary": item.get("summary_sentence"),
                }
                for item in candidates
            ],
        }
