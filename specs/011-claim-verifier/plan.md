# Implementation Plan: Claim Verifier and Agent Tools

**Branch**: `011-claim-verifier` | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-claim-verifier/spec.md`

## Summary

This slice adds the code that decides whether an agent's claim is proven, and the read-only tools the 012
agents use to collect evidence. No model is involved anywhere in 011.

What it adds:

- **Verifier** (`graphora/verify/`): `Claim` and `Verdict` types (R3, R4) and `verify(claims, ix, text)`.
  Dependency and chain claims are checked against graph edges at the cited line, with the imported name when
  given (R5). Definition and mention claims are checked against the stored file text (R6). Query result
  claims (count, member, rank) are checked by re-running the same graph question (R7). Statuses are
  `verified`, `heuristic` and `rejected`; a rejected verdict carries a fixed reason and a hint.
- **Agent tools** (`graphora/tools/`): six plain functions with MCP names (`find_definitions`, `read_lines`,
  `dependents`, `impact`, `neighbors`, `cycles`), a fixed `TOOLS` list of names and descriptions for 012 to wrap
  (R8). Answers are trimmed to 20 items, 60 lines and 4,000 characters, file text is framed as data (R9), and
  every answer returns ready-to-verify claims (R10).
- **Query layer**: `queries.matches_symbol`, the public name of the existing symbol rule (R5).

What it does not change: the graph schema, the store schema, fixtures, the HTTP API, the MCP server, the CLI.

## Technical Context

**Language/Version**: Python ≥ 3.12 (unchanged)

**Primary Dependencies**: none new (R2). Uses NetworkX through `graph/queries.py` and the 005 store

**Storage**: none new. File text is read from the 005 PostgreSQL store through `Store.get_file`

**Testing**: pytest. Synthetic graphs for every reason and status; golden tests over every fixture's
`expected.json` and `queries.json`; store tests marked `db`; one performance test marked `slow` (R11)

**Target Platform**: library inside the backend; called in process by 012 agents; CI offline with PostgreSQL

**Project Type**: library modules in the existing backend

**Performance Goals**: SC-005 — 100 claims on the largest fixture in < 1 s

**Constraints**: read-only; deterministic verdicts and tool answers; no model, network or disk reads in the
verifier; tool answers ≤ 20 items, 60 lines, 4,000 characters

**Scale/Scope**: one snapshot per call; tens of claims per agent answer

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Never execute analyzed code | Pass | verifier and tools read the graph and stored text only; no tool writes anything |
| II. Deterministic output | Pass | verdicts in claim order, proof edges sorted, canonical JSON; repeat tests (FR-013) |
| III. Provenance on every edge | Pass | a verdict's proof carries edges with full provenance (FR-004) |
| IV. Honest confidence | Pass | `heuristic` status, `fact` only for `verified`, unresolved edges never prove (FR-005, FR-008) |
| V. Facts by code, words by LLM | Pass | the verifier is plain code and checks file, line, symbol and edge exactly as the principle says |
| VI. Analyzed content is data | Pass | fixed tool descriptions, framed file text, bounded output (R9) |
| VII. One graph query layer | Pass | targets, symbols, definitions and query claims go through `graph/queries.py`; only the symbol rule is made public |
| VIII. Golden tests | Pass | claims built from hand-written `expected.json` and `queries.json` of every fixture; agent-facing tests assert structure (citations verify) |

Post-design re-check: still passes. Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/011-claim-verifier/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── verifier.md
│   └── agent-tools.md
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── src/graphora/
│   ├── graph/queries.py                   # + matches_symbol (public name of _matches)
│   ├── verify/                            # new
│   │   ├── __init__.py                    # verify, verify_served, store_text, Claim, Verdict, dumps
│   │   ├── claims.py                      # Step, Claim, Check, Line, Verdict, Reason, validation, JSON
│   │   ├── graph_checks.py                # dependency, chain and query claims
│   │   └── text_checks.py                 # TextSource, store_text, definition and mention claims
│   └── tools/                             # new
│       ├── __init__.py                    # TOOLS, tools_for, ToolSpec, ToolResult, LineRef
│       ├── limits.py                      # MAX_ITEMS, MAX_LINES, MAX_CHARS
│       └── agent.py                       # the six tools, descriptions, trimming, citations
└── tests/
    ├── unit/test_verify_claims.py         # validation, JSON round trip, determinism
    ├── unit/test_verify_graph.py          # dependency, chain, query claims on synthetic graphs
    ├── unit/test_verify_text.py           # definition, mention claims with a fake TextSource
    ├── unit/test_tools.py                 # arguments, trimming, framing, errors, citations (fake text)
    ├── golden/test_verify_fixtures.py     # every fixture: expected.json edges, queries.json (no db)
    ├── golden/test_verify_store.py        # marked db: definitions, mentions, tool citations verify
    └── integration/test_verify_performance.py   # marked slow, SC-005
```

**Structure Decision**: `verify/` is named in CLAUDE.md's target layout; `tools/` is new and owned by Anna,
kept outside Ulyana's `agents/` so 012 only imports it (R1). Query changes stay in `graph/` (constitution VII).

## Coordination

- The `Claim` / `Verdict` shapes (data-model.md, contracts/verifier.md) and the tool contract are the round 4
  sync with 012: Ulyana reviews them in PR #30 before implementation starts.
- `store/` is Ulyana's; 011 only calls `Store.get_file`.
- LangChain is not added here; 012 adds it and wraps `TOOLS` (contracts/agent-tools.md).
- CLAUDE.md is not changed: no new commands.

## Commits

A commit after every plan and tasks phase, and more than one per phase where a phase has separable parts
(for example types, then graph checks, then text checks). Small lowercase English messages.

## Complexity Tracking

No constitution violations.
