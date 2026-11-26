# Contract: Agents (`graphora.agents`)

Python entry point used by the CLI now and by `/ask` (013) later. Types: [data-model.md](../data-model.md).

```python
ask(
    question: str,
    served: Served,                       # graphora.mcp.served: graph index, optional store
    *,
    model: BaseChatModel | None = None,   # None → model_from_setting(setting)
    setting: str | None = None,           # None → $GRAPHORA_MODEL or "ollama:qwen3:8b"
    summary: bool = True,
    on_event: Callable[[TraceEvent], None] | None = None,
) -> Run                                  # Run(answer: Answer, trace: tuple[TraceEvent, ...])

model_from_setting(setting: str) -> BaseChatModel     # agents/model.py; raises ModelUnavailable
class ModelUnavailable(Exception): setting, address, reason
```

## Guarantees

- `question` must be non-empty after stripping, else `ValueError` before any model call.
- Read-only: only the 011 tools and `verify_served` touch the snapshot; nothing is written.
- Every `answer.facts` item's claim verifies `verified` against `served` (re-checkable by the caller), and
  every fact has a `cite`: `path:line@snapshot`, or `<question>(<target>)@<snapshot>` for a query claim.
- `answer.likely` holds only `heuristic` verdicts; `answer.hypotheses` only `rejected` ones.
- At most `MAX_TOOL_CALLS` tool calls, `MAX_REVISIONS` revisions, `MAX_MODEL_CALLS` model calls.
- A `ModelUnavailable` or other model exception during the run does not escape `ask`: the run ends with
  `end = model_failed` and the parts built so far. `model_from_setting` raises it for an unknown provider or
  a missing integration package, before the run.
- Same `question`, `served` and model replies → equal `Run` (and identical `to_dict` JSON).
- `on_event` is called once per trace event, in order, before `ask` returns; an exception in it ends the run
  like a model failure.

## Role prompts and tools

| Role | Tools bound | Model calls | Output to state |
|---|---|---|---|
| explorer | `find_definitions`, `read_lines` (store only), `dependents` | ≤ 6 per turn | evidence, citations |
| analyst | `dependents`, `impact`, `neighbors`, `cycles`; then claims phase with no tools | tool loop ≤ 5, then 1 claims call (also when the tool budget is spent) | evidence, citations, claims |
| reviewer | none (code) | 0 | verdicts, hypotheses, task, route |
| answer | none | 0 or 1 (summary) | answer, end |

Tool messages: `ToolResult.text`, then `citations:` and one line per citation `[cN] <cite> → <target or
symbol>` (heuristic-capable lines keep the 011 `(likely)` mark). The whole message is at most
`MAX_TOOL_MESSAGE_CHARS` (5,000): citation lines over 160 characters are shortened in the middle with `…`,
and the list is cut by whole lines with `(… N more citations)`; cut citations keep their ids in the state. Invalid call → `error: <message>`;
budget spent → `error: tool budget spent, write your result now`.

Revision task (explorer, rounds ≥ 1), fixed format:

```
Revision 1 of 2. These claims were not proven; find evidence that proves or corrects them:
h1: dependency frontend/src/api.ts:1 → backend/app/api.py — no_edge (no edge in the graph)
h2: dependency backend/app/api.py:5 → backend/app/models.py — edge_not_on_line (hint: line 3)
```
