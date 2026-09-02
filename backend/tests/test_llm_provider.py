from types import SimpleNamespace

import httpx
import pytest
from anthropic import APIStatusError, APITimeoutError, RateLimitError

from app.config import get_settings
from app.llm.provider import AnthropicProvider, OpenAIProvider, ProviderError, get_provider


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_fake_provider_is_the_safe_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    get_settings.cache_clear()
    assert get_provider().name == "mock"


def test_anthropic_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ALLOW_EXTERNAL_LLM", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="ALLOW_EXTERNAL_LLM"):
        get_provider()


def test_openai_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("ALLOW_EXTERNAL_LLM", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="ALLOW_EXTERNAL_LLM"):
        get_provider()


def test_openai_requires_key_after_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ALLOW_EXTERNAL_LLM", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        get_provider()


def test_anthropic_requires_key_after_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ALLOW_EXTERNAL_LLM", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        get_provider()


def test_anthropic_requires_all_routed_model_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ALLOW_EXTERNAL_LLM", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_FAST_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_BALANCED_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEEP_MODEL", raising=False)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="ANTHROPIC_FAST_MODEL"):
        get_provider()


def test_anthropic_sdk_retries_are_disabled_in_favor_of_worker_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}
    for name, value in {
        "LLM_PROVIDER": "anthropic",
        "ALLOW_EXTERNAL_LLM": "true",
        "ANTHROPIC_API_KEY": "test-key",
        "ANTHROPIC_FAST_MODEL": "fast-test",
        "ANTHROPIC_BALANCED_MODEL": "balanced-test",
        "ANTHROPIC_DEEP_MODEL": "deep-test",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        "app.llm.provider.Anthropic",
        lambda **kwargs: captured.update(kwargs) or SimpleNamespace(),
    )
    get_settings.cache_clear()

    assert get_provider().name == "anthropic"
    assert captured["timeout"] == 20.0
    assert captured["max_retries"] == 0


def test_anthropic_rejects_overlapping_sdk_retry_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in {
        "LLM_PROVIDER": "anthropic",
        "ALLOW_EXTERNAL_LLM": "true",
        "ANTHROPIC_API_KEY": "test-key",
        "ANTHROPIC_FAST_MODEL": "fast-test",
        "ANTHROPIC_BALANCED_MODEL": "balanced-test",
        "ANTHROPIC_DEEP_MODEL": "deep-test",
        "ANTHROPIC_SDK_MAX_RETRIES": "1",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="must remain 0"):
        get_provider()


def test_anthropic_provider_requests_and_validates_structured_output() -> None:
    captured = {}

    class Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                usage=SimpleNamespace(input_tokens=120, output_tokens=45),
                content=[
                    SimpleNamespace(
                        text='{"risk_level":"medium","applicability":"unknown",'
                        '"summary":"검토 필요","rationale":"근거 확인 필요",'
                        '"counter_considerations":[],"review_questions":[],'
                        '"cited_evidence_ids":["verified:1"]}'
                    )
                ]
            )

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.client = SimpleNamespace(messages=Messages())
    result = provider.assess(
        {"category": "test", "rationale": "test"},
        [{"evidence_id": "verified:1"}],
        "claude-test-model",
    )
    assert result["cited_evidence_ids"] == ["verified:1"]
    assert captured["model"] == "claude-test-model"
    assert captured["max_tokens"] == 600
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert provider.last_call_metadata()["input_tokens"] == 120
    assert provider.last_call_metadata()["output_tokens"] == 45
    assert provider.last_call_metadata()["prompt_version"] == "assessment-v1"
    assert "content" not in provider.last_call_metadata()


def test_anthropic_provider_blocks_unmasked_pii_before_network_call() -> None:
    called = False

    class Messages:
        def create(self, **kwargs):
            nonlocal called
            called = True

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.client = SimpleNamespace(messages=Messages())
    with pytest.raises(ProviderError, match="OUTBOUND_PII_BLOCKED") as caught:
        provider.assess(
            {"category": "test", "rationale": "주민번호 900101-1234567"},
            [{"evidence_id": "verified:1"}],
            "claude-test-model",
        )
    assert not caught.value.retryable
    assert not called


def test_openai_provider_uses_non_stored_structured_response() -> None:
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "id": "resp_test",
                "model": "gpt-test-model",
                "usage": {"input_tokens": 90, "output_tokens": 40},
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"risk_level":"medium","applicability":"unknown",'
                                    '"summary":"검토 필요","rationale":"근거 확인 필요",'
                                    '"counter_considerations":[],"review_questions":[],'
                                    '"cited_evidence_ids":["verified:1"]}'
                                ),
                            }
                        ],
                    }
                ],
            }

    class Client:
        @staticmethod
        def post(endpoint, **kwargs):
            captured.update({"endpoint": endpoint, **kwargs})
            return Response()

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = Client()
    provider._last_call = {}
    result = provider.assess(
        {"category": "test", "rationale": "masked"},
        [{"evidence_id": "verified:1"}],
        "gpt-test-model",
    )

    assert result["cited_evidence_ids"] == ["verified:1"]
    assert captured["endpoint"] == "https://api.openai.com/v1/responses"
    assert captured["json"]["store"] is False
    assert captured["json"]["text"]["format"]["type"] == "json_schema"
    assert captured["json"]["text"]["format"]["strict"] is True
    assert provider.last_call_metadata()["input_tokens"] == 90
    assert provider.last_call_metadata()["output_tokens"] == 40
    assert provider.last_call_metadata()["stored"] is False
    assert "content" not in provider.last_call_metadata()


def test_openai_provider_reviews_masked_clause_context_with_strict_schema() -> None:
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "id": "resp_context",
                "model": "gpt-test-model",
                "usage": {"input_tokens": 300, "output_tokens": 120},
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"candidates":[{"section_id":"article-7",'
                                    '"rule_id":"R11_DEEMED_CONSENT",'
                                    '"evidence_quote":"계속 사용하면 동의한 것으로 본다",'
                                    '"rationale":"명시적 의사표시 없이 동의를 간주할 가능성",'
                                    '"review_question":"거절 선택권이 있는가?",'
                                    '"confidence":"high","counter_considerations":[]}]}'
                                ),
                            }
                        ],
                    }
                ],
            }

    class Client:
        @staticmethod
        def post(endpoint, **kwargs):
            captured.update({"endpoint": endpoint, **kwargs})
            return Response()

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = Client()
    provider._last_call = {}
    result = provider.review_context(
        [
            {
                "section_id": "article-7",
                "label": "제7조",
                "text": "계속 사용하면 동의한 것으로 본다",
            }
        ],
        [{"rule_id": "R11_DEEMED_CONSENT", "name": "묵시적 동의"}],
        "gpt-test-model",
    )

    assert result["candidates"][0]["rule_id"] == "R11_DEEMED_CONSENT"
    assert captured["json"]["store"] is False
    assert captured["json"]["text"]["format"]["name"] == "fincontract_context_review"
    assert provider.last_call_metadata()["prompt_version"] == "context-review-v1"


def test_openai_provider_summarizes_masked_review_results_with_strict_schema() -> None:
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                "id": "resp_summary",
                "model": "gpt-test-model",
                "usage": {"input_tokens": 180, "output_tokens": 45},
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"lines":["금리 변경 위험 신호 2건이 확인되었습니다.","관련 조항의 변경 조건을 우선 검토해야 합니다."]}',
                            }
                        ],
                    }
                ],
            }

    class Client:
        @staticmethod
        def post(endpoint, **kwargs):
            captured.update({"endpoint": endpoint, **kwargs})
            return Response()

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = Client()
    provider._last_call = {}
    result = provider.summarize_review(
        {
            "rule_finding_count": 2,
            "candidate_finding_count": 0,
            "top_categories": ["금리 변경"],
        },
        "gpt-test-model",
    )

    assert len(result["lines"]) == 2
    assert result["lines"][0].startswith("금리 변경")
    assert captured["json"]["store"] is False
    assert captured["json"]["text"]["format"]["name"] == "fincontract_review_summary"
    assert provider.last_call_metadata()["prompt_version"] == "review-summary-v1"


def test_openai_provider_blocks_unmasked_pii_before_network_call() -> None:
    class Client:
        @staticmethod
        def post(*args, **kwargs):
            raise AssertionError("network call must not occur")

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = Client()
    provider._last_call = {}
    with pytest.raises(ProviderError, match="OUTBOUND_PII_BLOCKED") as caught:
        provider.assess(
            {"category": "test", "rationale": "주민번호 900101-1234567"},
            [{"evidence_id": "verified:1"}],
            "gpt-test-model",
        )
    assert not caught.value.retryable


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (429, "LLM_RATE_LIMITED", True),
        (500, "LLM_UNAVAILABLE", True),
        (400, "LLM_REQUEST_REJECTED", False),
    ],
)
def test_openai_provider_classifies_http_failures(
    status_code: int,
    expected_code: str,
    retryable: bool,
) -> None:
    class Response:
        pass

    Response.status_code = status_code

    class Client:
        @staticmethod
        def post(*args, **kwargs):
            return Response()

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = Client()
    provider._last_call = {}
    with pytest.raises(ProviderError, match=expected_code) as caught:
        provider.assess(
            {"category": "test", "rationale": "masked"},
            [{"evidence_id": "verified:1"}],
            "gpt-test-model",
        )
    assert caught.value.retryable is retryable


def test_openai_provider_classifies_exhausted_quota_as_non_retryable() -> None:
    class Response:
        status_code = 429

        @staticmethod
        def json():
            return {"error": {"code": "insufficient_quota"}}

    class Client:
        @staticmethod
        def post(*args, **kwargs):
            return Response()

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = Client()
    provider._last_call = {}
    with pytest.raises(ProviderError, match="LLM_QUOTA_EXCEEDED") as caught:
        provider.assess(
            {"category": "test", "rationale": "masked"},
            [{"evidence_id": "verified:1"}],
            "gpt-test-model",
        )
    assert not caught.value.retryable


@pytest.mark.parametrize("response_text", ["", "{}", "not-json"])
def test_anthropic_provider_rejects_empty_or_invalid_schema(response_text: str) -> None:
    class Messages:
        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(text=response_text)], usage=None)

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.client = SimpleNamespace(messages=Messages())
    with pytest.raises(ProviderError, match="LLM_SCHEMA_INVALID") as caught:
        provider.assess(
            {"category": "test", "rationale": "masked"},
            [{"evidence_id": "verified:1"}],
            "claude-test-model",
        )
    assert not caught.value.retryable


@pytest.mark.parametrize("failure_code", ["timeout", "rate_limit"])
def test_anthropic_provider_classifies_transient_failures(failure_code: str) -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    class Messages:
        def create(self, **kwargs):
            if failure_code == "timeout":
                raise APITimeoutError(request=request)
            response = httpx.Response(429, request=request)
            raise RateLimitError("limited", response=response, body=None)

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.client = SimpleNamespace(messages=Messages())
    expected = "LLM_UNAVAILABLE" if failure_code == "timeout" else "LLM_RATE_LIMITED"
    with pytest.raises(ProviderError, match=expected) as caught:
        provider.assess(
            {"category": "test", "rationale": "masked"},
            [{"evidence_id": "verified:1"}],
            "claude-test-model",
        )
    assert caught.value.retryable


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [(500, "LLM_UNAVAILABLE", True), (400, "LLM_REQUEST_REJECTED", False)],
)
def test_anthropic_provider_classifies_other_api_statuses(
    status_code: int,
    expected_code: str,
    retryable: bool,
) -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    class Messages:
        def create(self, **kwargs):
            response = httpx.Response(status_code, request=request)
            raise APIStatusError("failed", response=response, body=None)

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.client = SimpleNamespace(messages=Messages())
    with pytest.raises(ProviderError, match=expected_code) as caught:
        provider.assess(
            {"category": "test", "rationale": "masked"},
            [{"evidence_id": "verified:1"}],
            "claude-test-model",
        )
    assert caught.value.retryable is retryable
