"""LLM providers with an explicit, fail-closed external-provider boundary."""

from __future__ import annotations

import json
from typing import Any, Literal, Protocol

from anthropic import Anthropic
from pydantic import BaseModel, Field

from app.config import get_settings


class Provider(Protocol):
    """Common assessment contract implemented by fake and external providers."""
    name: str

    def assess(
        self, rule_signal: dict[str, Any], evidence: list[dict[str, Any]], model: str
    ) -> dict[str, Any]:
        """Return one schema-compatible assessment for masked, grounded input."""
        ...


class AssessmentOutput(BaseModel):
    """Strict schema that prevents free-form provider output entering the pipeline."""
    risk_level: Literal["low", "medium", "high"]
    applicability: Literal["applicable", "not_applicable", "unknown"]
    summary: str = Field(min_length=1, max_length=1000)
    rationale: str = Field(min_length=1, max_length=2000)
    counter_considerations: list[str] = Field(max_length=10)
    review_questions: list[str] = Field(max_length=10)
    cited_evidence_ids: list[str] = Field(min_length=1, max_length=20)


class FakeProvider:
    """Produce deterministic synthetic assessments for offline tests and demos."""
    # "fake" is the configuration value; retain "mock" in user-facing output
    # to make synthetic agent results unmistakable.
    name = "mock"

    def assess(self, rule_signal: dict[str, Any], evidence: list[dict[str, Any]], model: str) -> dict[str, Any]:
        """Build a stable review-oriented assessment citing every supplied item."""
        return {
            "risk_level": "medium",
            "applicability": "unknown",
            "summary": f"{rule_signal['category']} 관련 위험 신호가 있어 계약 전체 문맥의 검토가 필요합니다.",
            "rationale": rule_signal["rationale"],
            "counter_considerations": ["개별 협상 여부", "법령상 허용 사유", "사전 통지와 선택권 제공 여부"],
            "review_questions": ["고객에게 실질적인 거절 또는 해지 선택권이 제공됩니까?"],
            "cited_evidence_ids": [item["evidence_id"] for item in evidence],
        }


class AnthropicProvider:
    """Call Claude with JSON-schema constrained output after explicit opt-in."""
    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        self.client = Anthropic(api_key=api_key)

    def assess(self, rule_signal: dict[str, Any], evidence: list[dict[str, Any]], model: str) -> dict[str, Any]:
        """Assess a masked rule signal using only the retrieved evidence supplied."""
        prompt = {
            "task": "Return a cautious Korean JSON assessment, never a legal conclusion.",
            "rule_signal": rule_signal,
            "evidence": evidence,
            "required_keys": ["risk_level", "applicability", "summary", "rationale", "counter_considerations", "review_questions", "cited_evidence_ids"],
        }
        response = self.client.messages.create(
            model=model,
            max_tokens=600,
            messages=[{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": AssessmentOutput.model_json_schema(),
                }
            },
        )
        text = "".join(block.text for block in response.content if hasattr(block, "text"))
        return AssessmentOutput.model_validate_json(text).model_dump()


def get_provider() -> Provider:
    """Select a provider and fail closed unless every external-call guard is set."""
    settings = get_settings()
    if settings.llm_provider == "fake":
        return FakeProvider()
    if settings.llm_provider != "anthropic":
        raise RuntimeError("LLM_PROVIDER must be 'fake' or 'anthropic'")
    if not settings.allow_external_llm:
        raise RuntimeError("Anthropic is disabled: set ALLOW_EXTERNAL_LLM=true explicitly")
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when Anthropic is enabled")
    missing_models = [
        name
        for name, value in {
            "ANTHROPIC_FAST_MODEL": settings.anthropic_fast_model,
            "ANTHROPIC_BALANCED_MODEL": settings.anthropic_balanced_model,
            "ANTHROPIC_DEEP_MODEL": settings.anthropic_deep_model,
        }.items()
        if not value
    ]
    if missing_models:
        raise RuntimeError(f"Required Anthropic model settings are missing: {', '.join(missing_models)}")
    return AnthropicProvider(settings.anthropic_api_key)
