# Data Model: Agents

Types in `graphora/agents/`. Frozen dataclasses unless noted; `to_dict` drops `None` fields; JSON with sorted
keys, as the 011 types. `Claim`, `Verdict`, `ToolResult` are the 011 types, unchanged. Research: [research.md](research.md).

## Limits (`agents/limits.py`)

| Name | Value | Rule |
|---|---|---|
| `MAX_TOOL_CALLS` | 15 | tool calls requested in the run, valid or not |
| `MAX_REVISIONS` | 2 | revise routes taken |
| `MAX_MODEL_CALLS` | 30 | model calls in the run (tool loops, claims, summary) |
| `MAX_TURN_MODEL_CALLS` | 6 | model calls in one role turn |
| `MAX_SUMMARY_SENTENCES` | 5 | asked of the model; not enforced by code |

## AgentState (LangGraph state, a `TypedDict`)

| Field | Type | Written by |
|---|---|---|
| `question` | str | input |
| `snapshot` | str | input |
| `evidence` | list[Evidence] | explorer, analyst |
| `citations` | dict[str, Claim] | explorer, analyst: run-wide ids `c1, c2, …` in order of appearance |
| `claims` | list[Stated] | analyst |
| `verdicts` | dict[str, Verdict] | reviewer, keyed by claim key |
| `hypotheses` | list[Hypothesis] | reviewer |
| `task` | str \| None | reviewer: revision task for the explorer (fixed format, no repository text) |
| `tool_calls`, `model_calls`, `revisions` | int | loops, reviewer |
| `round` | int | reviewer; 0 for the first explorer → analyst pass |
| `end` | EndReason \| None | set once |
| `trace` | list[TraceEvent] | every node, append-only |

List fields use an append reducer; counters are replaced. No field holds a timestamp.

## Evidence

| Field | Type | Rule |
|---|---|---|
| `role` | `explorer \| analyst` | |
| `tool` | str | a name from `graphora.tools.TOOLS` |
| `args` | dict | validated arguments, sorted keys |
| `citation_ids` | tuple[str, ...] | ids given to `result.citations`, in order |
| `cut`, `error` | bool, str \| None | from the `ToolResult` |

The tool's `text` goes into the model messages only, not into `Evidence` or the trace.

## Stated (a claim proposed by the Analyst)

| Field | Type | Rule |
|---|---|---|
| `claim` | Claim | built by code from the reply item; `snapshot` always the run's snapshot |
| `key` | str | canonical JSON of `claim.to_dict()` without `statement`; used for dedupe (FR-012) |
| `round` | int | |
| `revises` | str \| None | `hN` of an open hypothesis |

### ClaimsReply (pydantic, the structured reply of the claims phase)

`claims: list[ClaimItem]`, at most 20. `ClaimItem` fields: `statement` (str), and exactly one of:

- `cite` (str, `c\d+`): use the citation with that id as the claim;
- `question` + `target` (optional for `cycles`) + `count` or `member` (+ `distance`, `rank`): a 011 query claim;
- `path` + `line` + `target` (+ `name`): a dependency claim with one step;

plus `revises` (optional `h\d+`). An item that fits none of these, or cites an unknown id, is not a claim: it
is recorded in the trace as `claim_invalid` with a fixed reason and dropped. A reply that fails to parse
counts as one model call and gives no claims.

## Hypothesis

| Field | Type | Rule |
|---|---|---|
| `id` | str | `h1, h2, …` in order of first rejection |
| `claim` | Claim | |
| `reason` | Reason | from the verdict |
| `hint` | str \| None | from the verdict |
| `tries` | int | revisions in which it was open |
| `open` | bool | false once a verified claim names it in `revises` |

## Answer

| Field | Type | Rule |
|---|---|---|
| `question`, `snapshot` | str | |
| `facts` | tuple[Item, ...] | verified claims, in first-stated order |
| `likely` | tuple[Item, ...] | heuristic claims, same order |
| `hypotheses` | tuple[Item, ...] | open hypotheses, by id |
| `summary` | str | model summary if it passed the check, else the code summary |
| `summary_source` | `model \| code` | |
| `end` | EndReason | |
| `counts` | dict | `tool_calls`, `model_calls`, `revisions` |

`Item`: `text` (fixed template sentence per claim kind, R7), `cite` (`claim.cite()` or `None` for query
claims), `claim` (Claim), `reason` and `hint` for hypotheses.

`render_answer(answer) -> str`: plain text with headings `Facts`, `Likely`, `Hypotheses (not proven)`,
`Summary`, and a last line `snapshot <id> · ended: <reason>`. Empty parts print `(none)`.

## EndReason

`answered` (review passed or nothing left to revise) · `revisions_spent` · `budget_spent` (tool calls) ·
`model_budget_spent` · `model_failed` · `no_claims`.

## TraceEvent

| Field | Type | Present for |
|---|---|---|
| `n` | int | all; 1-based order |
| `kind` | `role_start \| tool_call \| claim \| claim_invalid \| verdict \| revision \| hypothesis \| summary \| end` | all |
| `role` | `explorer \| analyst \| reviewer \| answer` | all |
| `tool`, `args`, `citation_ids`, `cut`, `error` | | `tool_call` |
| `key`, `cite`, `status`, `reason`, `hint` | | `claim`, `verdict`, `hypothesis` |
| `detail` | str | fixed-format note (`revision 1 of 2: 2 claims`, `budget spent`, end reason) |

The trace never contains tool text, model text, or file content.

## State transitions

```
explorer(round r) → analyst(round r) → reviewer
reviewer: rejected ∧ revisions < 2 ∧ tool_calls < 15 → explorer(round r+1)   [revision]
reviewer: otherwise → answer → END
any node: model_calls ≥ 30 or ModelUnavailable → answer (end = model_budget_spent | model_failed)
```
