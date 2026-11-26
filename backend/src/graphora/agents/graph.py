"""The agents' state graph: explorer → analyst → reviewer → (revise → explorer | answer) (specs/012-agents
research R2, contracts/agents.md)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from graphora.agents import prompts
from graphora.agents.answer import build_answer, parts, summary_input
from graphora.agents.claims import ClaimsReply, to_stated
from graphora.agents.limits import MAX_MODEL_CALLS, MAX_REVISIONS, MAX_TOOL_CALLS, MAX_TURN_MODEL_CALLS
from graphora.agents.model import model_failure, model_from_setting, setting_from_env
from graphora.agents.review import end_reason, review
from graphora.agents.state import AgentState, Run, TraceEvent
from graphora.agents.tools import CitationIds, RoleTools, citation_block, refuse, run_tool_call

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from graphora.mcp.served import Served

OnEvent = Callable[[TraceEvent], None]


class _Recorder:
    """Numbers trace events and passes each to `on_event` as it happens; a failing callback ends the run."""

    def __init__(self, on_event: OnEvent | None) -> None:
        self.n = 0
        self.on_event = on_event
        self.pending: list[TraceEvent] = []
        self.failed = False
        self.error: str | None = None

    def emit(self, kind: str, role: str, **fields: Any) -> None:
        self.n += 1
        event = TraceEvent(self.n, kind, role, **fields)
        self.pending.append(event)
        if self.on_event is not None and not self.failed:
            try:
                self.on_event(event)
            except Exception as exc:
                self.failed = True
                self.error = f"trace callback failed: {type(exc).__name__}: {exc}"[:300]

    def flush(self) -> list[TraceEvent]:
        out, self.pending = self.pending, []
        return out


def _text(message: BaseMessage) -> str:
    """The reply text without reasoning that some models write inline before `</think>`."""
    content = message.content
    if not isinstance(content, str):
        content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return content.rsplit("</think>", 1)[-1].strip()


class _Agents:
    def __init__(
        self,
        served: Served,
        model: BaseChatModel,
        setting: str,
        summary: bool,
        on_event: OnEvent | None,
        stop: Callable[[], bool] | None = None,
    ) -> None:
        self.served = served
        self.stop = stop
        self.model = model
        self.setting = setting
        self.summary = summary
        self.rec = _Recorder(on_event)
        self.ids = CitationIds()
        self.error: str | None = None
        self.tools = {role: RoleTools(role, served) for role in ("explorer", "analyst")}

    # -- shared pieces -------------------------------------------------------------------------------------------

    def _failed(self, state: AgentState) -> str | None:
        return "model_failed" if self.rec.failed else state.get("failed")

    def _stopped(self, counters: dict[str, Any]) -> bool:
        """True once the caller asked to stop: no new model or tool call is made after that."""
        if counters["failed"] == "stopped" or (self.stop is not None and self.stop()):
            counters["failed"] = "stopped"
            return True
        return False

    def _call(self, runnable: Any, messages: list[BaseMessage], counters: dict[str, Any], parse: bool = False) -> Any:
        """One model call within the run budget. None when stopped, the budget is spent, the model failed or (with
        `parse`) the structured reply could not be read; only the last leaves `failed` unset."""
        if self._stopped(counters):
            return None
        if counters["model_calls"] >= MAX_MODEL_CALLS:
            counters["failed"] = "model_budget_spent"
            return None
        counters["model_calls"] += 1
        try:
            return runnable.invoke(messages)
        except Exception as exc:
            known = model_failure(exc, self.setting)
            if parse and isinstance(exc, (ValidationError, ValueError)) and known is None:
                return None
            counters["failed"] = "model_failed"
            if self.error is None:
                self.error = known.message if known is not None else f"model {self.setting} failed: {type(exc).__name__}: {exc}"[:300]
            return None

    def _tool_loop(self, role: str, messages: list[BaseMessage], counters: dict[str, Any], cap: int) -> str:
        """Model call → tool calls → repeat, until a reply without tool calls, the turn cap or a budget."""
        tools = self.tools[role]
        bound = self.model.bind_tools(list(tools.tools.values()))
        notes = ""
        for _ in range(cap):
            if counters["failed"] or self.rec.failed or counters["tool_calls"] >= MAX_TOOL_CALLS:
                break
            reply = self._call(bound, messages, counters)
            if reply is None:
                break
            messages.append(reply)
            calls = list(getattr(reply, "tool_calls", None) or ())
            broken = list(getattr(reply, "invalid_tool_calls", None) or ())
            if not calls and not broken:
                notes = _text(reply)
                break
            for call in calls + [dict(b, args=None) for b in broken]:
                if self._stopped(counters):
                    break
                if counters["tool_calls"] >= MAX_TOOL_CALLS:
                    message, evidence = refuse(call, role)
                else:
                    counters["tool_calls"] += 1
                    message, evidence = run_tool_call(call, tools, self.ids, role)
                messages.append(message)
                counters["evidence"].append(evidence)
                self.rec.emit(
                    "tool_call",
                    role,
                    tool=evidence.tool,
                    args=evidence.args,
                    citation_ids=evidence.citation_ids,
                    cut=evidence.cut,
                    error=evidence.error,
                )
        return notes

    @staticmethod
    def _counters(state: AgentState) -> dict[str, Any]:
        return {
            "tool_calls": state.get("tool_calls", 0),
            "model_calls": state.get("model_calls", 0),
            "failed": state.get("failed"),
            "evidence": [],
        }

    def _update(self, counters: dict[str, Any], **more: Any) -> dict[str, Any]:
        failed = "model_failed" if self.rec.failed else counters["failed"]
        return {
            "tool_calls": counters["tool_calls"],
            "model_calls": counters["model_calls"],
            "failed": failed,
            "evidence": counters["evidence"],
            "citations": dict(self.ids.claims),
            "trace": self.rec.flush(),
        } | more

    # -- nodes ---------------------------------------------------------------------------------------------------

    def explorer(self, state: AgentState) -> dict[str, Any]:
        self.rec.emit("role_start", "explorer", detail=f"round {state.get('round', 0)}")
        counters = self._counters(state)
        messages: list[BaseMessage] = [
            SystemMessage(prompts.EXPLORER),
            HumanMessage(prompts.explorer_task(state["question"], state.get("task"))),
        ]
        notes = self._tool_loop("explorer", messages, counters, MAX_TURN_MODEL_CALLS)
        return self._update(counters, notes=notes)

    def analyst(self, state: AgentState) -> dict[str, Any]:
        rnd = state.get("round", 0)
        self.rec.emit("role_start", "analyst", detail=f"round {rnd}")
        counters = self._counters(state)
        cited = citation_block(list(self.ids.claims), self.ids.claims, 4000)
        open_ids = [h.id for h in state.get("hypotheses") or () if h.open]
        messages: list[BaseMessage] = [
            SystemMessage(prompts.ANALYST),
            HumanMessage(prompts.analyst_task(state["question"], state.get("task"), state.get("notes") or "", cited)),
        ]
        self._tool_loop("analyst", messages, counters, MAX_TURN_MODEL_CALLS - 1)
        stated: list[Any] = []
        if not counters["failed"] and not self.rec.failed:
            cited = citation_block(list(self.ids.claims), self.ids.claims, 4000)
            messages.append(HumanMessage(prompts.claims_task(open_ids, cited)))
            reply = self._call(self.model.with_structured_output(ClaimsReply), messages, counters, parse=True)
            if reply is None and not counters["failed"]:
                self.rec.emit("claim_invalid", "analyst", detail="the claims reply could not be read")
            elif reply is not None:
                try:
                    reply = reply if isinstance(reply, ClaimsReply) else ClaimsReply.model_validate(reply)
                except ValidationError:
                    reply = ClaimsReply()
                    self.rec.emit("claim_invalid", "analyst", detail="the claims reply could not be read")
                stated, invalid = to_stated(reply, dict(self.ids.claims), state["snapshot"], rnd, set(open_ids))
                for n, reason in invalid:
                    self.rec.emit("claim_invalid", "analyst", detail=f"claim {n}: {reason}")
                for s in stated:
                    self.rec.emit("claim", "analyst", key=s.key, cite=s.claim.cite(), detail=s.revises)
        return self._update(counters, claims=stated)

    def reviewer(self, state: AgentState) -> dict[str, Any]:
        self.rec.emit("role_start", "reviewer", detail=f"round {state.get('round', 0)}")
        state = dict(state, failed=self._failed(state))  # type: ignore[assignment]
        update = review(state, self.served, lambda kind, **f: self.rec.emit(kind, "reviewer", **f))
        return update | {"failed": self._failed(state), "trace": self.rec.flush()}

    def answer(self, state: AgentState) -> dict[str, Any]:
        self.rec.emit("role_start", "answer")
        counters = self._counters(state)
        facts, likely, _ = parts(state)
        summary = None
        if self.summary and (facts or likely) and not counters["failed"] and not self.rec.failed:
            reply = self._call(
                self.model,
                [SystemMessage(prompts.SUMMARY), HumanMessage(summary_input(state["question"], facts, likely))],
                counters,
            )
            if isinstance(reply, AIMessage):
                summary = _text(reply)
        failed = "model_failed" if self.rec.failed else counters["failed"]
        final = dict(state, model_calls=counters["model_calls"], failed=failed)
        end = end_reason(final)  # type: ignore[arg-type]
        answer = build_answer(final, summary, end)  # type: ignore[arg-type]
        self.rec.emit("summary", "answer", detail=answer.summary_source)
        self.rec.emit("end", "answer", detail=end)
        return {"model_calls": counters["model_calls"], "failed": failed, "answer": answer, "trace": self.rec.flush()}

    def build(self) -> Any:
        graph = StateGraph(AgentState)
        graph.add_node("explorer", self.explorer)
        graph.add_node("analyst", self.analyst)
        graph.add_node("reviewer", self.reviewer)
        graph.add_node("answer", self.answer)
        graph.add_edge(START, "explorer")
        graph.add_edge("explorer", "analyst")
        graph.add_edge("analyst", "reviewer")
        graph.add_conditional_edges("reviewer", lambda s: s["route"], {"revise": "explorer", "answer": "answer"})
        graph.add_edge("answer", END)
        return graph.compile()


def ask(
    question: str,
    served: Served,
    *,
    model: BaseChatModel | None = None,
    setting: str | None = None,
    summary: bool = True,
    on_event: OnEvent | None = None,
    stop: Callable[[], bool] | None = None,
) -> Run:
    """Answer one question about one snapshot (contracts/agents.md). Model failures end the run, never raise.
    `stop` is checked before every model and tool call; once true the run makes no new call and ends `stopped`."""
    if not question.strip():
        raise ValueError("question must not be empty")
    setting = setting or setting_from_env()
    if model is None:
        model = model_from_setting(setting)
    agents = _Agents(served, model, setting, summary, on_event, stop)
    start: AgentState = {
        "question": question.strip(),
        "snapshot": served.snapshot,
        "evidence": [],
        "claims": [],
        "trace": [],
        "verdicts": {},
        "hypotheses": [],
        "task": None,
        "tool_calls": 0,
        "model_calls": 0,
        "revisions": 0,
        "round": 0,
        "failed": None,
    }
    final = agents.build().invoke(start, {"recursion_limit": 3 * (MAX_REVISIONS + 1) + 5})
    error = agents.error or agents.rec.error if final["answer"].end == "model_failed" else None
    return Run(final["answer"], tuple(final["trace"]), error)
