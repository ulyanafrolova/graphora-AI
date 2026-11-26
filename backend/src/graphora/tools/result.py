"""What an agent tool returns (specs/011-claim-verifier data-model.md § ToolSpec, ToolResult, LineRef)."""

from __future__ import annotations

from dataclasses import dataclass

from graphora.verify import Claim


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str


@dataclass(frozen=True)
class LineRef:
    path: str
    start: int
    end: int
    snapshot: str


@dataclass(frozen=True)
class ToolResult:
    """`text` goes to the model; `citations` and `lines` go to the agent state, ready to verify."""

    text: str
    citations: tuple[Claim, ...] = ()
    lines: LineRef | None = None
    cut: bool = False
    next: int | None = None
    error: str | None = None


def failure(message: str) -> ToolResult:
    return ToolResult(text=f"error: {message}", error=message)
