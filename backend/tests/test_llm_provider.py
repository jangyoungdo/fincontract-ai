from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.llm.provider import AnthropicProvider, get_provider


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


def test_anthropic_provider_requests_and_validates_structured_output() -> None:
    captured = {}

    class Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
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
    assert captured["output_config"]["format"]["type"] == "json_schema"
