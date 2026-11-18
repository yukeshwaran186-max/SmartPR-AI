"""Tests for lazy and configurable LLM initialization."""

import pytest

from app import refactor


def test_openai_model_is_created_lazily_and_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[dict[str, object]] = []

    def fake_chat_openai(**kwargs: object) -> object:
        created.append(kwargs)
        return object()

    monkeypatch.setattr(refactor, "ChatOpenAI", fake_chat_openai)
    monkeypatch.setattr(refactor, "LLM_BASE_URL", None)
    monkeypatch.setattr(refactor, "OPENAI_MODEL", "test-openai-model")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert created == []
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        refactor.get_llm()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    refactor.get_llm()
    assert created == [
        {
            "model": "test-openai-model",
            "api_key": "test-key",
            "temperature": 0,
        }
    ]


def test_custom_openai_compatible_endpoint_uses_optional_model_and_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[dict[str, object]] = []

    def fake_chat_openai(**kwargs: object) -> object:
        created.append(kwargs)
        return object()

    monkeypatch.setattr(refactor, "ChatOpenAI", fake_chat_openai)
    monkeypatch.setattr(refactor, "LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(refactor, "LLM_API_KEY", "local-key")
    monkeypatch.setattr(refactor, "LLM_MODEL", "local-model")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    refactor.get_llm()

    assert created == [
        {
            "model": "local-model",
            "api_key": "local-key",
            "base_url": "http://localhost:11434/v1",
            "temperature": 0,
        }
    ]
