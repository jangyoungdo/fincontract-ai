"""LLM providers with an explicit, fail-closed external-provider boundary."""

from __future__ import annotations

import json
from typing import Any, Protocol

from anthropic import Anthropic

from app.config import get_settings


class Provider(Protocol):
    name: str

    def assess(self, rule_signal: dict[str, Any], evidence: list[dict[str, Any]], model: str) -> dict[str, Any]: ...


class FakeProvider:
    # "fake" is the configuration value; retain "mock" in user-facing output
    # to make synthetic agent results unmistakable.
    name = "mock"

    def assess(self, rule_signal: dict[str, Any], evidence: list[dict[str, Any]], model: str) -> dict[str, Any]:
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
    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        self.client = Anthropic(api_key=api_key)

    def assess(self, rule_signal: dict[str, Any], evidence: list[dict[str, Any]], model: str) -> dict[str, Any]:
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
        )
        text = "".join(block.text for block in response.content if hasattr(block, "text"))
        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError("Anthropic response must be a JSON object")
        return result


def get_provider() -> Provider:
    settings = get_settings()
    if settings.llm_provider == "fake":
        return FakeProvider()
    if settings.llm_provider != "anthropic":
        raise RuntimeError("LLM_PROVIDER must be 'fake' or 'anthropic'")
    if not settings.allow_external_llm:
        raise RuntimeError("Anthropic is disabled: set ALLOW_EXTERNAL_LLM=true explicitly")
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when Anthropic is enabled")
    return AnthropicProvider(settings.anthropic_api_key)
