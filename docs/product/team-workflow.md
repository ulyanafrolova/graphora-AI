# Graphora — Team Workflow

How the two of us split and synchronize work. Change this file by pull request, agreed by both.

## Principles

- The repository is the only shared memory. Each of us works with our own coding agent, and the agents do
  not see each other's chats. Anything agreed verbally goes into the repository: a spec, an ADR in
  `docs/adr/`, the constitution or `CLAUDE.md`.
- Work is split by module ownership. Each module has one owner who writes and merges it; the other
  person reviews. Parallel branches then touch different folders and rarely collide.
- The graph contract (`schema/graph.schema.json`) and the fixtures in `fixtures/repos/` are the
  boundary between producing and consuming graphs. Consumers build against fixture graphs and never wait
  for the analyzer.

## Module owners

| Owner | Modules in `backend/src/graphora/` and elsewhere |
|---|---|
| Ulyana | `ingest/walk.py`, `ingest/snapshot.py`, `detect/`, `adapters/`, `resolve/`, `graph/build.py`, `graph/model.py`, `graph/serialize.py`, `schema/`, `store/`, `api/`, `agents/`, the end-to-end pipeline, the frontend bridge |
| Anna | `ingest/` sources (GitHub, ZIP, safe extraction), graph queries in `graph/`, `mcp/`, `verify/`, history (hotspots), CI and tooling |
| Both | `frontend/`, `bench/`, shared files listed under Rules |

Changing a module you do not own: open the pull request and request the owner's review.

## Order of work

| Round | Anna | Ulyana |
|---|---|---|
| 0 | Dev tooling: CI, `Makefile`, ruff, this file | Review; protect `main` (required `checks`) |
| sync | Agree: source fetching returns a folder plus a known snapshot id; `build()` accepts it | |
| 1 | 002 repo ingest: GitHub URL and ZIP | 003 TS/JS analysis (schema v2) |
| 2 | 004 graph queries (NetworkX) | 005 storage and HTTP API |
| 3 | 006 MCP server | 007 end-to-end pipeline |
| sync | Agree: `Claim`, `Verdict`, agent state | |
| 4 | 008 claim verifier and agent tools | 009 agents |
| 5 | 011 hotspots | 010 `/ask` with streaming |
| 6–7 | Frontend together, 013 benchmark | Frontend together, 012 HTTP bridge |

## Feature cycle

1. Reserve the feature: open a GitHub issue with the feature number and name (`NNN-short-name`) and
   assign it. Spec Kit picks the next free number automatically, so reserve first to avoid two `002`s.
2. `/speckit-specify`, then open a draft pull request with `spec.md` only. The other person reviews the
   spec before planning: fixing an idea here costs minutes.
3. `/speckit-clarify` if needed, then `/speckit-plan`, `/speckit-tasks` and `/speckit-analyze`.
4. `/speckit-implement`. `make check` must pass locally.
5. Mark the pull request ready, get it reviewed by the other person, and merge to `main`.

## Rules

- One feature = one branch = one pull request. Keep branches short: days, not weeks.
- `git pull` on `main` before starting work, and rebase on `main` before asking for review.
- Do not edit someone else's open spec or branch. Comment in the pull request instead.
- Shared files change only in a separate, agreed pull request:
  - `.specify/memory/constitution.md`
  - `CLAUDE.md`
  - `schema/graph.schema.json`, which also requires a schema version bump and updates to all consumers
  - `fixtures/repos/*/expected.json`
  - this file
- Weekly 15–20 minute sync: what is done, what is next, and where we block each other.
