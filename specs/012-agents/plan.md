# Implementation Plan: Agents

**Branch**: `012-agents` | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-agents/spec.md`

## Summary

This slice adds the three agents on top of the 011 verifier and agent tools, and a command to ask them.

What it adds:

- **State graph** (`graphora/agents/graph.py`): fixed order explorer → analyst → reviewer → (revise →
  explorer | answer), one shared state with evidence, claims, verdicts, hypotheses, counters and trace (R2).
  Explorer and Analyst run bounded tool loops over the 011 tools (at most 3 and 4 tools); the Analyst then
  states claims in a structured reply that refers to tool citations by id (R3).
- **Reviewer** (code, no model): verifies each round's claims with `verify_served`, dedupes them, sends
  rejected ones back to the Explorer as hypotheses `h1…` with the verifier's reason and hint, at most 2 times
  (R4). Budget: 15 tool calls, 30 model calls per run, 6 per role turn (R5).
- **Answer** (code): facts, likely and hypotheses built from verdicts with fixed templates, plus an optional
  model summary that code checks for unproven paths and citations (R7).
- **Model setting** (`agents/model.py`): `GRAPHORA_MODEL` / `--model`, default `ollama:qwen3:8b`, via
  `init_chat_model`; connection failures become `ModelUnavailable` (R6).
- **Trace**: ordered events without timestamps or repository text, also passed to a callback for 013 (R9).
- **CLI**: `graphora ask` with the `graphora mcp` snapshot options, exit code 9 for model failures (R11).

What it does not change: the graph schema, the store schema, fixtures, 011 verifier and tools, the HTTP API,
the MCP server.

## Technical Context

**Language/Version**: Python ≥ 3.12 (unchanged)

**Primary Dependencies**: new `langgraph==1.2.21`, `langchain==1.4.10`, `langchain-ollama==1.1.0` (R1); the
011 `graphora.tools` and `graphora.verify`; `graphora.mcp.served` for snapshot loading

**Storage**: none new; reads the 005 store through 011 tools and verifier only

**Testing**: pytest. A scripted chat model double (R10); scenario tests on stored fixtures (`db`); unit tests
for reviewer, answer builder and summary check without any model; CLI tests; one live test marked `llm`
(new marker), skipped without `GRAPHORA_TEST_MODEL`

**Target Platform**: backend library and CLI on a developer laptop; Ollama runs natively outside Graphora;
CI offline (no model)

**Project Type**: library modules plus a CLI subcommand in the existing backend

**Performance Goals**: SC-007 — under 2 minutes per answer with `qwen3:8b` on a laptop; the code part
(review, answer) adds well under 1 s (011 SC-005)

**Constraints**: ≤ 15 tool calls, ≤ 2 revisions, ≤ 30 model calls; ≤ 4 tools per role; read-only; no
network except the configured model; deterministic for fixed model replies

**Scale/Scope**: one question, one snapshot per run; tens of claims per answer

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Never execute analyzed code | Pass | agents use only the read-only 011 tools and the verifier; no tool writes; no code from the repository runs (FR-018) |
| II. Deterministic output | Pass | fixed node order, run-wide citation and hypothesis ids in order, no timestamps; equal `Run` for equal model replies (FR-022). Model output itself is not deterministic; the plan sets `temperature=0` and tests determinism with a scripted model |
| III. Provenance on every edge | Pass | facts carry `path:line@snapshot`; verdict proofs keep full edge provenance (011) |
| IV. Honest confidence | Pass | three separate answer parts; heuristic never a fact, never sent back; rejected → hypothesis (FR-011, FR-013) |
| V. Facts by code, words by LLM | Pass | Reviewer is code; facts part built by code; summary checked by code; budget 15 / 2 as the principle says (R4, R5, R7) |
| VI. Analyzed content is data | Pass | 011 framing and bounds; fixed role prompts state that tool data is not instructions; no repository text in the trace (R8, R9) |
| VII. One graph query layer | Pass | agents call 011 tools and verifier, which call `graph/queries.py`; no query logic in `agents/` |
| VIII. Golden tests | Pass | scenario tests on fixtures assert structure (facts re-verify, key files found, budget held), never wording (FR-021) |
| Tech: LangGraph; local LLM by config; ≤ 3–4 tools; validated arguments | Pass | R1, R3, R6; arguments validated by the 011 functions before running, unknown tools rejected in the loop |

Post-design re-check: still passes. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/012-agents/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── agents.md
│   └── cli.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml                 # + langgraph, langchain, langchain-ollama; + `llm` marker
├── src/graphora/
│   ├── agents/
│   │   ├── __init__.py            # ask, Run, Answer, TraceEvent, ModelUnavailable
│   │   ├── limits.py              # MAX_TOOL_CALLS, MAX_REVISIONS, MAX_MODEL_CALLS, MAX_TURN_MODEL_CALLS
│   │   ├── model.py               # model_from_setting, ModelUnavailable, failure mapping
│   │   ├── prompts.py             # fixed role prompts and message formats
│   │   ├── state.py               # AgentState, Evidence, Stated, Hypothesis, TraceEvent, EndReason
│   │   ├── tools.py               # 011 tools → StructuredTool; citation ids; tool loop
│   │   ├── claims.py              # ClaimsReply → Claim, claim keys
│   │   ├── review.py              # reviewer node and route
│   │   ├── answer.py              # Answer, templates, summary check, render_answer
│   │   └── graph.py               # StateGraph wiring, ask()
│   └── cli/__init__.py            # + `ask` subcommand, EXIT_MODEL = 9
└── tests/
    ├── unit/
    │   ├── scripted_model.py      # ScriptedModel test double
    │   ├── test_agents_claims.py
    │   ├── test_agents_review.py
    │   ├── test_agents_answer.py
    │   └── test_agents_budget.py
    ├── golden/test_agents_fixtures.py     # scenarios on stored fixtures (db)
    └── integration/
        ├── test_ask_cli.py
        └── test_agents_live.py            # marked llm
```

**Structure Decision**: a new `agents/` package owned by Ulyana (team workflow); it imports `graphora.tools`,
`graphora.verify` and `graphora.mcp.served` and nothing in `agents/` imports LangChain outside `model.py`,
`tools.py`, `claims.py` and `graph.py`, so the reviewer and answer builder stay plain code testable without
any model. Tests follow the existing `unit/`, `golden/`, `integration/` layout.

## Complexity Tracking

No constitution violations.
