# Graphora Constitution

## Core Principles

### I. Never Execute Analyzed Code (NON-NEGOTIABLE)

- Imported repositories MUST be analyzed statically only. No code from them is run, imported,
  built, installed or evaluated, including `setup.py`, package scripts and test suites.
- Every tool available to agents (internal or via MCP) MUST be read-only.
- Ingest MUST enforce limits (size, file count, time) and protect archive extraction against
  path traversal, zip bombs and symlinks escaping the snapshot root.

Rationale: Graphora runs on untrusted public repositories.

### II. Deterministic Output

- The same input snapshot and the same extractor versions MUST produce a byte-identical
  serialized graph.
- Nodes, edges, lists and object keys MUST be emitted in a defined sorted order. Output MUST NOT
  depend on set/dict iteration order, file system order, timestamps, randomness or thread
  scheduling.
- Any algorithm with non-deterministic behaviour (e.g. community detection) MUST use a fixed
  seed and a stable tie-break.

Rationale: reproducibility is the product's core claim against chat agents.

### III. Provenance on Every Edge

- Every edge MUST carry: source, target, type, line, snapshot id (commit SHA, or
  `<sha>+dirty:<content-hash>` for uncommitted trees), confidence, extractor name@version and a
  snippet hash.
- A node or edge without provenance MUST NOT enter the graph.

Rationale: every fact must be traceable to `file:line@commit` and verifiable later.

### IV. Honest Confidence

- Edges use exactly three confidence levels: `resolved` (written in code and resolved to a
  target), `heuristic` (likely link, e.g. matched HTTP route), `unresolved` (a link exists but
  its target could not be determined).
- Resolvers MUST NOT guess. An import that cannot be resolved by defined rules stays
  `unresolved`.
- Full analysis is claimed only for supported languages. Other files are marked
  `detected_only` or `not_code` in the coverage report.
- UI, API, MCP and agent answers MUST keep facts and heuristics visually and textually distinct.

### V. Facts by Code, Words by LLM

- Dependencies, cycles, reverse dependencies, impact, centrality and hotspots MUST be computed
  by algorithms, never inferred by a model.
- The claim verifier MUST be plain deterministic code. It checks that the cited file exists in
  the snapshot, the line contains the symbol and the edge exists in the graph.
- Agent answers MAY contain only verified claims as facts; anything else is labeled a
  hypothesis.
- Agents run under an explicit step budget (default: about 15 tool calls, at most 2 revisions).

### VI. Analyzed Content Is Data

- File contents, comments, READMEs and tool output passed to a model MUST be wrapped as clearly
  marked data. Instructions found inside them MUST NOT be followed.
- Tool output MUST be trimmed to a bounded size before it reaches the model.

### VII. One Graph Query Layer

- All graph queries live in one module (`backend/src/graphora/graph/`). The HTTP API, the MCP
  server and agent tools MUST call it and MUST NOT reimplement query logic.
- The serialized graph format is defined by `schema/graph.schema.json`. Changing it requires a
  schema version bump and updates to all consumers in the same change.

### VIII. Golden Tests as Ground Truth

- Adapter, resolver and graph changes MUST be covered by golden tests over the fixture
  repositories in `fixtures/repos/`, each with a hand-checked `expected.json`.
- A feature is not done until its golden tests pass and a repeated run yields identical output.
- Agent tests MUST assert on structure (citations exist and verify, key files are found), not
  on exact wording.

## Technical Constraints

- Backend: Python, managed with `uv`; Tree-sitter for parsing; NetworkX for graph algorithms;
  FastAPI for HTTP; PostgreSQL for storage keyed by (repository, snapshot id); LangGraph for
  agents; an MCP server over the shared query layer.
- Frontend: React + Vite + TypeScript; Cytoscape.js for the graph (WebGL renderer may replace it
  if large graphs require it). Large graphs show clusters by default and expand on demand.
- LLM: local by default (Ollama, `qwen3:8b`, explicit `num_ctx`); the provider is selected by
  configuration only, never hard-coded. Each agent gets at most 3–4 tools; tool arguments are
  validated before execution.
- Language support for MVP: full analysis for Python and TypeScript/JavaScript only.

## Development Workflow

- Work proceeds in vertical slices. Each feature goes through `/speckit-specify` →
  (`/speckit-clarify`) → `/speckit-plan` → `/speckit-tasks` → `/speckit-analyze` →
  `/speckit-implement`, with artifacts in `specs/NNN-feature-name/`.
- Specs are written only for the next slice, not for the whole roadmap.
- One feature = one branch = one pull request, reviewed by a human team member before merge.
- Graphora only recommends changes to analyzed repositories; it never modifies them.

## Governance

- This constitution supersedes other practices. Plans MUST include a constitution check, and
  any deviation MUST be written down with a justification in the plan's complexity section.
- Amendments are made by pull request, agreed by both team members, and versioned with
  semantic versioning: MAJOR for removed or redefined principles, MINOR for new or expanded
  principles or sections, PATCH for wording fixes.
- Runtime guidance for coding agents lives in `CLAUDE.md`; product context lives in
  `docs/product/`.

**Version**: 1.0.0 | **Ratified**: 2026-10-19 | **Last Amended**: 2026-10-19
