"""A chat model that replays scripted replies, for agent tests without a live model (specs/012-agents R10)."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, ConfigDict, Field


class Script:
    """The shared reply queue and a record of every call: (kind, messages, bound tool names)."""

    def __init__(self, replies: list[Any]) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, list[BaseMessage], tuple[str, ...]]] = []

    def pop(self, kind: str, messages: list[BaseMessage], tools: tuple[str, ...]) -> Any:
        self.calls.append((kind, list(messages), tools))
        if not self.replies:
            raise AssertionError("script exhausted")
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


class ScriptedModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    script: Script
    tools: tuple[str, ...] = Field(default=())

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        reply = self.script.pop("chat", messages, self.tools)
        if isinstance(reply, str):
            reply = AIMessage(content=reply)
        if not isinstance(reply, AIMessage):
            raise AssertionError(f"expected a chat reply, got {type(reply).__name__}")
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedModel:
        return ScriptedModel(script=self.script, tools=tuple(t.name for t in tools))

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        def run(messages: Any) -> Any:
            reply = self.script.pop("structured", list(messages), ())
            if isinstance(reply, dict):
                return schema.model_validate(reply)
            if not isinstance(reply, BaseModel):
                raise AssertionError(f"expected a structured reply, got {type(reply).__name__}")
            return reply

        return RunnableLambda(run)


_ids = iter(range(1, 1_000_000))


def call(tool: str, /, **args: Any) -> AIMessage:
    """A reply with one tool call."""
    return calls((tool, args))


def calls(*items: tuple[str, dict[str, Any]]) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"t{next(_ids)}"} for n, a in items])


def scripted(*replies: Any) -> tuple[ScriptedModel, Script]:
    script = Script(list(replies))
    return ScriptedModel(script=script), script
