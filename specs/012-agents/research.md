# Research: Agents

Decisions for [spec.md](spec.md). Each one: decision, rationale, alternatives considered.

## R1. Dependencies and pins

**Decision**: add `langgraph==1.2.21`, `langchain==1.4.10` (for `init_chat_model`) and
`langchain-ollama==1.1.0` as runtime dependencies; `langchain-core` comes in through them and is pinned by
`uv.lock`. Exact pins, versions released at least two weeks before planning (2026-11-26). Other providers
(for example `langchain-google-genai` for the Gemini fallback) are not added; a developer who sets another
provider installs its integration package (`uv add`), and the error for a missing package names it.

**Rationale**: the constitution fixes LangGraph for agents and a configurable provider; `init_chat_model`
gives the one-line provider switch from the product context. Exact, slightly older pins follow the project's
pinning practice after the tree-sitter 0.26.0 incident (#8).

**Alternatives**: the newest releases (`langgraph` 1.2.24, `langchain` 1.5.2, `langchain-ollama` 1.2.0, all
under a week old) — rejected for now, can be bumped in a tooling PR; the `ollama` client directly without
LangChain — rejected, it loses the provider switch and the tool-calling abstraction.

## R2. Shape of the state graph

**Decision**: one `StateGraph` with four nodes and fixed edges:

```
START → explorer → analyst → reviewer ─┬─ revise → explorer
                                       └─ answer → END
```

`explorer` and `analyst` are each a bounded tool-calling loop written inside the node (model call → validate
tool calls → run tools → repeat until the model stops calling tools or a limit is hit). `reviewer` and the
route after it are plain code. `answer` is code plus one optional model call for the summary (R7).

**Rationale**: FR-004 needs a fixed order that model text cannot change; one shared budget (FR-006) is
easiest to enforce when the loop that runs tools is ours. Writing the loop in the node keeps every counter in
the shared state and every step in the trace.

**Alternatives**: `create_agent` / prebuilt ReAct agents per role — rejected: each has its own loop and
recursion limit, so a shared tool-call budget and per-call validation need hooks into their internals; a
supervisor node choosing the next role with the model — rejected: the order would depend on model text.

## R3. Tool split and how claims are stated

**Decision**: two phases per model role.

- **Explore/analyze phase**: Explorer gets `find_definitions`, `read_lines` (only when text is stored),
  `dependents`; Analyst gets `dependents`, `impact`, `neighbors`, `cycles` (FR-003). Tools are the 011
  functions wrapped as LangChain `StructuredTool`s from `graphora.tools.TOOLS`.
- **Claims phase** (Analyst only): one more model call with no tools bound, asking for a structured reply
  (`with_structured_output`, a pydantic `ClaimsReply`). Each claim either refers to a citation id that a tool
  returned (`"cite": "c7"`), or is a query claim (`question`, `target`, `count` or `member`), or gives its
  own dependency steps (`path`, `line`, `target`, optional `name`). A claim in a revision round may name the
  hypothesis it revises (`"revises": "h2"`).

Every tool result shown to the model (at most `MAX_TOOL_MESSAGE_CHARS = 5000` characters in total, see
data-model.md § Limits) ends with a short citation list `[c7] api/routes.py:3@abc → auth/service.py`,
with run-wide ids in order of appearance, so the model never retypes paths and lines.

**Rationale**: at most 4 tools per role (constitution); a structured reply for claims keeps the tool lists
short and makes claims parseable; citation ids remove the most common small-model mistake (wrong path or
line). A model may still type its own citation (FR-009); it is verified the same way.

**Alternatives**: a `state_claim` tool in the tool loop — rejected: a fifth tool for the Analyst; claims in
free text parsed by regex — rejected: fragile, and statement text must never decide facts; Explorer also
stating claims — rejected for 012: one role producing claims keeps the revision loop simple (Explorer feeds
evidence, Analyst restates).

## R4. Review and revision

**Decision**: the Reviewer node verifies all claims of the current round with `verify_served` in one call.
Claims are deduplicated by their canonical JSON without `statement` (FR-012); a claim seen before reuses its
verdict. Routing:

- no rejected claims, or `revisions == MAX_REVISIONS`, or tool budget spent → `answer`;
- otherwise → `revise`: `revisions += 1`, the rejected claims become open hypotheses `h1, h2, …` with reason
  and hint, and the Explorer's next turn gets them as its task.

`heuristic` verdicts are never sent back (FR-011). A verified claim with `revises: hN` closes `hN`; open
hypotheses at the end go to the answer's hypotheses part with the number of revisions tried.

**Rationale**: matches the product-context flow (weak claim back to Explorer, downgraded when the budget runs
out) with deterministic bookkeeping; the explicit `revises` link avoids guessing which new claim replaces
which old one.

**Alternatives**: matching revisions by statement similarity — rejected: non-deterministic and wording-based;
sending back to the Analyst instead of the Explorer — rejected: the issue and product context send it to the
Explorer, which owns file and symbol search.

## R5. Budget and limits

**Decision**: `agents/limits.py` holds `MAX_TOOL_CALLS = 15`, `MAX_REVISIONS = 2`, `MAX_MODEL_CALLS = 30` per
run and `MAX_TURN_MODEL_CALLS = 6` per role turn. Every requested tool call is counted before validation
(invalid and unknown calls count, FR-007); calls past the budget are not run, get the message "tool budget
spent", and end the turn. Once the budget is spent, later tool loops are skipped, but the Analyst's claims
call still runs while model calls remain, and the Reviewer reviews what was stated (FR-008). The Analyst's
tool loop may use at most `MAX_TURN_MODEL_CALLS - 1` model calls, so the claims call always has one left. LangGraph's `recursion_limit` is set from these numbers as a backstop only.

**Rationale**: FR-006/FR-007/SC-003; a per-turn model-call cap stops a model that loops without tools, the
run-wide cap stops the whole graph.

**Alternatives**: a wall-clock timeout — kept out of the graph (it breaks determinism); the CLI may add one
later.

## R6. Model configuration

**Decision**: one setting, `GRAPHORA_MODEL` (or `--model`), in `init_chat_model` form `provider:model`,
default `ollama:qwen3:8b`. For the `ollama` provider the agents pass `num_ctx=16384` and `temperature=0`
(overridable by `GRAPHORA_MODEL_CTX`); the Ollama address comes from the standard `OLLAMA_HOST`. Model
construction lives only in `agents/model.py`; tests pass a model object instead of a setting.

Connection failures (`httpx.ConnectError`, `ConnectionError`, Ollama "model not found") at any model call
become `ModelUnavailable(setting, address, reason)`; the run ends with end reason `model_failed` and the
answer built so far (FR-015); the CLI maps a failure before any answer to exit code 9.

**Rationale**: FR-016; 15 tool answers of ≤ 4,000 characters across turns need more than Ollama's small
default context, while each role turn sees only its own messages, so 16k tokens fit an 8B model on a laptop.

**Alternatives**: a config file — rejected: one value is enough; hard-coded `ChatOllama` — rejected by the
constitution.

## R7. Answer and summary check

**Decision**: the `answer` node builds the facts, likely and hypotheses parts by code from verdicts, with one
fixed sentence template per claim kind (for example "`api/routes.py` imports `auth/service.py`
(api/routes.py:3@abc)"; query claims: "`auth/service.py` has 3 direct dependents"). The model then gets these
parts (as data) and the question and writes a summary of at most 5 sentences. The summary is accepted only if
every path-like token (`[\w./-]+\.\w+`, node ids) it contains appears in the facts or likely parts and
every `path:line` it contains is a fact citation (likely links may be named by file, not by line; FR-014); otherwise it is replaced by a code
summary ("3 facts, 1 likely link, 1 hypothesis about `auth/service.py`"). `--no-summary` skips the model call.

**Rationale**: FR-013/FR-014: facts never depend on the model; the check is plain code and catches the
dangerous case (citing an unproven file or line). It checks names, not wording, and the plan says so.

**Alternatives**: no model summary at all — possible, kept as `--no-summary`; asking a second model to judge
the summary — rejected: facts by code.

## R8. Safety of model input

**Decision**: fixed role prompts in `agents/prompts.py` (English, no repository text) say that text between
file markers and inside tool results is data and never instructions. Tool results reach the model as the 011
`ToolResult.text` (already framed and trimmed) plus the citation list (≤ 20 short lines). Hypothesis reasons
and hints come from the verifier's fixed reasons. The question is the developer's own text and is passed as
the user message.

**Rationale**: constitution VI; the 011 bounds already apply.

## R9. Trace

**Decision**: `TraceEvent` values appended to `state.trace` in order, and also passed to an optional
`on_event` callback as they happen (013 streams them). No timestamps or durations in events. File text never
enters the trace: tool events keep the tool name, arguments, `cut`, `error` and the citation ids only.

**Rationale**: FR-019, FR-022 (identical traces), and the trace is safe to print.

## R10. Determinism and testing

**Decision**: a `ScriptedModel` test double (a LangChain `BaseChatModel` returning queued `AIMessage`s with
tool calls, and queued structured replies) in `tests/unit/scripted_model.py`. Scenario tests on stored fixtures:
`py-cycles` (what breaks), `mixed-fullstack` (the frontend claim with no TS → Python edge), `py-flat` (wrong
line then corrected), plus misbehaving scripts (unknown tool, broken args, endless tool calls, no tool calls,
model error). Assertions on structure only (FR-021). One live test marked `llm`, skipped unless
`GRAPHORA_TEST_MODEL` is set, checks budget and that every fact verifies (FR-023, SC-007).

**Rationale**: constitution VIII (structure, not wording); CI stays offline.

**Alternatives**: `GenericFakeChatModel` from langchain-core — rejected: no `bind_tools`; recorded live
transcripts — rejected: they break when prompts change.

## R11. Command line

**Decision**: `graphora ask QUESTION` with the snapshot options of `graphora mcp` (`--graph`, or
`--repository` + `--snapshot` [+ `--database`]), plus `--model`, `--no-summary`, `--json` and
`--trace FILE`. Exit codes reuse the existing ones and add `EXIT_MODEL = 9`. Details:
[contracts/cli.md](contracts/cli.md).

**Rationale**: FR-020, and the same snapshot loading (`from_graph_file`, `from_store`) as the MCP server.
