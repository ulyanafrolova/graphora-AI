"""The model setting and its failures (specs/012-agents research R6, tasks T004). Nothing is contacted."""

import httpx
import pytest

from graphora.agents.model import DEFAULT_MODEL, ModelUnavailable, model_failure, model_from_setting, setting_from_env


def test_default_setting(monkeypatch):
    monkeypatch.delenv("GRAPHORA_MODEL", raising=False)
    assert setting_from_env() == DEFAULT_MODEL == "ollama:qwen3:8b"
    monkeypatch.setenv("GRAPHORA_MODEL", "ollama:llama3.1:8b")
    assert setting_from_env() == "ollama:llama3.1:8b"


def test_ollama_model_options(monkeypatch):
    monkeypatch.delenv("GRAPHORA_MODEL_CTX", raising=False)
    model = model_from_setting("ollama:qwen3:8b")
    assert (model.model, model.num_ctx, model.temperature) == ("qwen3:8b", 16384, 0)
    monkeypatch.setenv("GRAPHORA_MODEL_CTX", "8192")
    assert model_from_setting("ollama:qwen3:8b").num_ctx == 8192


def test_unknown_provider_and_bad_setting():
    with pytest.raises(ModelUnavailable) as exc:
        model_from_setting("nope:x")
    assert exc.value.setting == "nope:x" and "nope" in exc.value.reason
    with pytest.raises(ModelUnavailable):
        model_from_setting("qwen3")


def test_missing_package():
    with pytest.raises(ModelUnavailable) as exc:
        model_from_setting("openai:gpt-4o")  # langchain-openai is not a dependency
    assert "langchain-openai" in exc.value.reason and exc.value.address == "the openai API"


def test_failure_mapping(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    found = model_failure(httpx.ConnectError("refused"), "ollama:qwen3:8b")
    assert found is not None and found.address == "http://127.0.0.1:11434" and found.reason == "cannot connect"
    assert found.message == "model ollama:qwen3:8b unavailable at http://127.0.0.1:11434: cannot connect"
    monkeypatch.setenv("OLLAMA_HOST", "10.0.0.2:9999")
    assert model_failure(ConnectionRefusedError(), "ollama:qwen3:8b").address == "http://10.0.0.2:9999"

    class ResponseError(Exception):
        pass

    missing = model_failure(ResponseError('model "qwen3:8b" not found, try pulling it first'), "ollama:qwen3:8b")
    assert missing is not None and "ollama pull qwen3:8b" in missing.reason
    try:
        try:
            raise httpx.ConnectError("refused")
        except httpx.ConnectError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert model_failure(outer, "ollama:qwen3:8b") is not None
    assert model_failure(KeyError("x"), "ollama:qwen3:8b") is None
