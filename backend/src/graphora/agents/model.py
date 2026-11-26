"""The one model setting and its failures (specs/012-agents research R6). The only module that names a provider."""

from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel

DEFAULT_MODEL = "ollama:qwen3:8b"
DEFAULT_CTX = 16384
_OLLAMA_DEFAULT = "http://127.0.0.1:11434"


class ModelUnavailable(Exception):
    def __init__(self, setting: str, address: str, reason: str) -> None:
        self.setting = setting
        self.address = address
        self.reason = reason
        self.message = f"model {setting} unavailable at {address}: {reason}"
        super().__init__(self.message)


def setting_from_env() -> str:
    return os.environ.get("GRAPHORA_MODEL") or DEFAULT_MODEL


def ollama_address() -> str:
    host = os.environ.get("OLLAMA_HOST") or _OLLAMA_DEFAULT
    return host if "://" in host else f"http://{host}"


def address(setting: str) -> str:
    provider = setting.partition(":")[0]
    return ollama_address() if provider == "ollama" else f"the {provider} API"


def model_from_setting(setting: str) -> BaseChatModel:
    """`provider:model`, e.g. `ollama:qwen3:8b`. Raises ModelUnavailable for an unknown provider or a missing
    integration package; nothing is contacted here."""
    from langchain.chat_models import init_chat_model

    provider, sep, name = setting.partition(":")
    if not sep or not provider or not name:
        raise ModelUnavailable(setting, "-", "expected provider:model, e.g. ollama:qwen3:8b")
    options: dict[str, object] = {}
    if provider == "ollama":
        options = {"num_ctx": int(os.environ.get("GRAPHORA_MODEL_CTX") or DEFAULT_CTX), "temperature": 0}
    try:
        return init_chat_model(name, model_provider=provider, **options)
    except ImportError as exc:
        raise ModelUnavailable(setting, address(setting), str(exc).split(". ")[0]) from exc
    except ValueError as exc:
        raise ModelUnavailable(setting, address(setting), str(exc).strip().splitlines()[0]) from exc


def model_failure(exc: BaseException, setting: str) -> ModelUnavailable | None:
    """A ModelUnavailable for a connection failure or a missing model anywhere in the exception chain."""
    import httpx

    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ModelUnavailable):
            return current
        if isinstance(current, (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError)):
            return ModelUnavailable(setting, address(setting), "cannot connect")
        if type(current).__name__ == "ResponseError" and "not found" in str(current).lower():
            name = setting.partition(":")[2]
            return ModelUnavailable(setting, address(setting), f"model not found (run `ollama pull {name}`)")
        current = current.__cause__ or current.__context__
    return None
