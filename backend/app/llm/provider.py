"""LLM providers with an explicit, fail-closed external-provider boundary."""

from __future__ import annotations

import json
import time
from typing import Any, Literal, Protocol

import httpx
from anthropic import Anthropic, APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import get_settings

PROMPT_VERSION = "assessment-v1"


class ProviderError(RuntimeError):
    """Expose only stable failure metadata to retry and review workflows."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class Provider(Protocol):
    """Common assessment contract implemented by fake and external providers."""
    name: str

    def assess(
        self,
        rule_signal: dict[str, Any],
        evidence: list[dict[str, Any]],
        model: str,
        max_tokens: int = 600,
    ) -> dict[str, Any]:
        """Return one schema-compatible assessment for masked, grounded input."""
        ...

    def last_call_metadata(self) -> dict[str, Any]:
        """Return non-content telemetry for the most recent assessment call."""
        ...


class AssessmentOutput(BaseModel):
    """Strict schema that prevents free-form provider output entering the pipeline."""
    model_config = ConfigDict(extra="forbid")

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

    def __init__(self) -> None:
        self._last_call = {"prompt_version": PROMPT_VERSION, "synthetic": True}

    def assess(
        self,
        rule_signal: dict[str, Any],
        evidence: list[dict[str, Any]],
        model: str,
        max_tokens: int = 600,
    ) -> dict[str, Any]:
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

    def last_call_metadata(self) -> dict[str, Any]:
        """Mark fake-provider usage without fabricating token or latency values."""
        return dict(self._last_call)


class AnthropicProvider:
    """Call Claude with JSON-schema constrained output after explicit opt-in."""
    name = "anthropic"

    def __init__(self, api_key: str, timeout_seconds: float = 20.0, max_retries: int = 0) -> None:
        self.client = Anthropic(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )
        self._last_call: dict[str, Any] = {}

    def assess(
        self,
        rule_signal: dict[str, Any],
        evidence: list[dict[str, Any]],
        model: str,
        max_tokens: int = 600,
    ) -> dict[str, Any]:
        """Assess a masked rule signal using only the retrieved evidence supplied."""
        prompt = {
            "task": "Return a cautious Korean JSON assessment, never a legal conclusion.",
            "prompt_version": PROMPT_VERSION,
            "rule_signal": rule_signal,
            "evidence": evidence,
            "required_keys": ["risk_level", "applicability", "summary", "rationale", "counter_considerations", "review_questions", "cited_evidence_ids"],
        }
        serialized_prompt = json.dumps(prompt, ensure_ascii=False)
        # Re-run the same conservative detector at the final outbound boundary.
        # Import lazily to avoid a package initialization cycle with the pipeline.
        from app.prototype.pii import mask_pii

        masking = mask_pii(serialized_prompt)
        if not masking.passed or masking.replacement_count:
            raise ProviderError("OUTBOUND_PII_BLOCKED", retryable=False)

        started = time.perf_counter()
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": serialized_prompt}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": AssessmentOutput.model_json_schema(),
                    }
                },
            )
        except RateLimitError as exc:
            raise ProviderError("LLM_RATE_LIMITED", retryable=True) from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise ProviderError("LLM_UNAVAILABLE", retryable=True) from exc
        except APIStatusError as exc:
            retryable = exc.status_code >= 500
            code = "LLM_UNAVAILABLE" if retryable else "LLM_REQUEST_REJECTED"
            raise ProviderError(code, retryable=retryable) from exc
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        text = "".join(block.text for block in response.content if hasattr(block, "text"))
        try:
            assessment = AssessmentOutput.model_validate_json(text).model_dump()
        except ValidationError as exc:
            raise ProviderError("LLM_SCHEMA_INVALID", retryable=False) from exc
        usage = getattr(response, "usage", None)
        self._last_call = {
            "prompt_version": PROMPT_VERSION,
            "model": model,
            "latency_ms": elapsed_ms,
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }
        return assessment

    def last_call_metadata(self) -> dict[str, Any]:
        """Return token and latency telemetry without prompt or response content."""
        return dict(self._last_call)


class OpenAIProvider:
    """Call the OpenAI Responses API with non-stored structured output."""

    name = "openai"
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        self.client = httpx.Client(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout_seconds,
        )
        self._last_call: dict[str, Any] = {}

    def assess(
        self,
        rule_signal: dict[str, Any],
        evidence: list[dict[str, Any]],
        model: str,
        max_tokens: int = 600,
    ) -> dict[str, Any]:
        """Assess one masked rule finding without sending document bytes or full text."""
        prompt = {
            "task": (
                "주어진 위험 신호와 검색 근거만 사용해 신중한 한국어 검토 의견을 작성하세요. "
                "위법·적법·무효를 확정하지 말고, 제공된 evidence_id만 인용하세요."
            ),
            "prompt_version": PROMPT_VERSION,
            "rule_signal": rule_signal,
            "evidence": evidence,
        }
        serialized_prompt = json.dumps(prompt, ensure_ascii=False)
        from app.prototype.pii import mask_pii

        masking = mask_pii(serialized_prompt)
        if not masking.passed or masking.replacement_count:
            raise ProviderError("OUTBOUND_PII_BLOCKED", retryable=False)

        payload = {
            "model": model,
            "store": False,
            "instructions": (
                "You are a contract-review assistant. Return only schema-valid JSON in Korean. "
                "Never make a final legal conclusion."
            ),
            "input": serialized_prompt,
            "max_output_tokens": max_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "fincontract_assessment",
                    "strict": True,
                    "schema": AssessmentOutput.model_json_schema(),
                }
            },
        }
        started = time.perf_counter()
        try:
            response = self.client.post(self.endpoint, json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ProviderError("LLM_UNAVAILABLE", retryable=True) from exc
        if response.status_code == 429:
            try:
                api_error_code = (response.json().get("error") or {}).get("code")
            except (AttributeError, TypeError, ValueError):
                api_error_code = None
            if api_error_code in {"insufficient_quota", "billing_hard_limit_reached"}:
                raise ProviderError("LLM_QUOTA_EXCEEDED", retryable=False)
            raise ProviderError("LLM_RATE_LIMITED", retryable=True)
        if response.status_code >= 500:
            raise ProviderError("LLM_UNAVAILABLE", retryable=True)
        if response.status_code >= 400:
            raise ProviderError("LLM_REQUEST_REJECTED", retryable=False)

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            body = response.json()
            text = self._output_text(body)
            assessment = AssessmentOutput.model_validate_json(text).model_dump()
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise ProviderError("LLM_SCHEMA_INVALID", retryable=False) from exc
        usage = body.get("usage") or {}
        self._last_call = {
            "prompt_version": PROMPT_VERSION,
            "model": body.get("model", model),
            "response_id": body.get("id"),
            "latency_ms": elapsed_ms,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "stored": False,
        }
        return assessment

    @staticmethod
    def _output_text(body: dict[str, Any]) -> str:
        parts: list[str] = []
        for item in body.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    parts.append(str(content["text"]))
        if not parts:
            raise ValueError("response contained no output_text")
        return "".join(parts)

    def last_call_metadata(self) -> dict[str, Any]:
        """Return only non-content telemetry for audit and cost measurement."""
        return dict(self._last_call)


def get_provider() -> Provider:
    """Select a provider and fail closed unless every external-call guard is set."""
    settings = get_settings()
    if settings.llm_provider == "fake":
        return FakeProvider()
    if settings.llm_provider == "openai":
        if not settings.allow_external_llm:
            raise RuntimeError("OpenAI is disabled: set ALLOW_EXTERNAL_LLM=true explicitly")
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when OpenAI is enabled")
        return OpenAIProvider(
            settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
        )
    if settings.llm_provider != "anthropic":
        raise RuntimeError("LLM_PROVIDER must be 'fake', 'openai', or 'anthropic'")
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
    if settings.anthropic_sdk_max_retries != 0:
        raise RuntimeError(
            "ANTHROPIC_SDK_MAX_RETRIES must remain 0; the worker owns the retry budget"
        )
    return AnthropicProvider(
        settings.anthropic_api_key,
        timeout_seconds=settings.anthropic_timeout_seconds,
        max_retries=settings.anthropic_sdk_max_retries,
    )
