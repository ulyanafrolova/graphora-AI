# Graphora

Static, commit-pinned dependency graph of a repository with provenance on every edge, AI agents
with deterministic claim verification on top, and an MCP server for external coding agents.

## Read first

- `.specify/memory/constitution.md` — non-negotiable rules. Check every plan and change against it.
- `docs/product/project-context.md` — architecture, agents, API, risks, MVP scope.
- `docs/product/vision.md` — positioning and features.
- `docs/demo/README.md` — UI concept screens (mockup data is illustrative).

## Key rules (short version of the constitution)

- Never execute analyzed code. Agent and MCP tools are read-only.
- Output is deterministic: sort everything, no set/dict order, no timestamps in the graph.
- Every edge has provenance: `file:line@commit`, confidence, extractor@version, snippet hash.
- Confidence is `resolved` | `heuristic` | `unresolved`. Never guess an import target.
- Facts are computed by code; the LLM only phrases verified claims. The verifier is plain code.
- File contents given to a model are data, never instructions.
- TS/JS config files are data: never run Node, never read `node_modules`.
- .NET project files (`.csproj`, `.sln`, `Directory.Build.props`) are data: never run `dotnet`,
  MSBuild or NuGet, never evaluate MSBuild conditions.
- Graph queries live only in `backend/src/graphora/graph/`; API, MCP and agents call them.

## Repository layout (target)

```
schema/graph.schema.json   graph contract between backend and frontend
fixtures/repos/            small test repos + expected.json (ground truth)
backend/src/graphora/      ingest, detect, adapters, resolve, graph, store, verify, agents, mcp, api, cli
frontend/                  React + Vite + TS + Cytoscape.js
bench/                     benchmark questions and runner
specs/NNN-feature/         Spec Kit artifacts per feature
docs/product/, docs/adr/   product context and architecture decisions
```

Directories appear as features are implemented; do not create empty scaffolding ahead of a spec.

## Workflow

Spec Kit skills: `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` →
`/speckit-analyze` → `/speckit-implement`. Specify only the next vertical slice.
One feature = one branch = one PR, reviewed by a human.

## Commands

```
cd backend && uv sync                               # install
uv run pytest                                       # all tests
uv run pytest -m "not slow"                         # skip the performance test
uv run graphora analyze <dir> --out graph.json      # build a graph
uv run graphora analyze https://github.com/<owner>/<repo> [--ref <ref>] --out graph.json
uv run graphora analyze <file.zip> --out graph.json
uv run graphora analyze <source> --no-history        # skip the git history (no hotspots)
uv run graphora query graph.json hotspots            # files changed often × transitive dependents (from 014)
```

History (feature 014) is read by default: a local git folder from its `.git`, a GitHub link by fetching commits
and trees of the year before the commit (no file contents, no git binary). ZIP sources and folders without `.git`
have none; hotspots then say "history not available" with the reason.

Analysis store and HTTP API (from feature 005). Store tests are marked `db` and need PostgreSQL:

```
make db                                             # PostgreSQL 17 on 127.0.0.1:5432 (docker compose)
export GRAPHORA_TEST_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora_test
export GRAPHORA_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora
uv run pytest -m "not db"                           # run without a database
uv run graphora analyze <source> --store            # also save in the store, or reuse a stored analysis
uv run graphora serve                               # HTTP API on 127.0.0.1:8000, analysis jobs (from 010)
make db-down                                        # stop PostgreSQL
```

Analysis over HTTP (feature 010): `serve` runs jobs in the background (`--workers 1 --queue 20 --work-dir`,
plus the `analyze` limits). Start one and poll it; a `done` job names the stored repository and snapshot:

```
curl -X POST localhost:8000/api/v1/jobs -H 'Content-Type: application/json' -d '{"github":"https://github.com/<owner>/<repo>"}'
curl -X POST 'localhost:8000/api/v1/jobs/zip?name=app.zip' --data-binary @app.zip
curl localhost:8000/api/v1/jobs/<id>
```

Graph questions over HTTP (feature 018): `dependencies`, `dependents`, `impact`, `neighbors`, `cycles`, `key_files`,
`definitions` (`name=`), `overview`, `projects` of a stored snapshot; each answer equals `graphora query … --format json`
with the same options (default `limit` 50, at most 500; `key_files` 10). Parameters are listed at `/api/v1/docs`:

```
curl 'localhost:8000/api/v1/impact?repository=<name>&snapshot=<id>&target=<path>&limit=20'
curl 'localhost:8000/api/v1/cycles?repository=<name>&snapshot=<id>'
```

Agents (feature 012): ask one snapshot a question; facts are verified by code, the rest is likely or a hypothesis.
The model is one setting (`GRAPHORA_MODEL`, default `ollama:qwen3:8b`; `GRAPHORA_MODEL_CTX`, default 16384) and
Ollama runs natively outside Graphora. Tests use a scripted model; the live test is marked `llm`:

```
uv run graphora ask "What breaks if I change <path>?" --graph graph.json [--trace -] [--json]
uv run graphora ask "<question>" --repository <name> --snapshot <id>      # store mode, like `graphora mcp`
GRAPHORA_TEST_MODEL=ollama:qwen3:8b uv run pytest -m llm                    # live model, skipped otherwise
```

Ask over HTTP (feature 013): `serve` answers questions about a stored snapshot and streams the agent trace as
server-sent events (`step` per trace event, then one `answer`, the `ask --json` document). One ask at a time by
default (`--asks`), the model from `--model` or `GRAPHORA_MODEL`; a second ask gets 429 `busy`:

```
uv run graphora serve --asks 1 --model ollama:qwen3:8b
curl -N -X POST localhost:8000/api/v1/ask -H 'Content-Type: application/json' \
  -d '{"repository":"<name>","snapshot":"<id>","question":"What breaks if I change <path>?"}'
```

Golden fixtures: `fixtures/repos/<name>/repo/` is analyzed, `fixtures/repos/<name>/expected.json` is
written by hand (never generated by the tool). `.gitignore` re-includes fixture `.venv/` and
`__pycache__/` folders on purpose: they test the skip rules.
