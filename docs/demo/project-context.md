# Graphora — Project Context

Working notes for the team: product idea, architecture, technical decisions, risks and pitch. Product-facing texts are in vision-en.md and vision-pl.md, and UI mockups are in README.md in this folder.

## 1. Product in one paragraph

Graphora is a web application that builds a deterministic, commit-pinned dependency graph of a Git repository and lets collaborating AI agents answer architecture questions on top of it. Every edge in the graph links back to the exact file and line it came from, and every agent claim is checked by code against the graph; anything that cannot be proven is labeled a hypothesis. The same graph queries are exposed through MCP, so external coding agents such as Claude Code or Cursor can use them.

Tagline: AI agents generate answers. Graphora gives them — and you — facts.

## 2. Positioning

Coding agents already explain code, so Graphora is not positioned as "AI that explains a codebase". The argument is:

- Agents now write most of the code, so the bottleneck is understanding and reviewing code nobody on the team wrote.
- Chat agents give one-off, non-reproducible answers that have to be verified again. Graphora gives computed facts: the same commit always gives the same graph.
- Graphora does not compete with coding agents; it gives them a map through MCP.

Key honesty principles: full analysis is claimed only for supported languages, facts and heuristics are always visually separated, and analyzed code is never executed.

## 3. How it works

Analysis runs once per commit, without an LLM:

1. Snapshot. Download the archive of a specific commit SHA. Apply limits (for example 50 MB, 5 000 files, 5 minutes) and skip node_modules, venv, dist and minified files. Protect ZIP extraction against path traversal, zip bombs and symlinks.
2. Language detection. Detect languages by extension and marker files (pyproject.toml, package.json, tsconfig.json). Each file gets a status: fully analyzed, detected only, or not code.
3. Adapters. Tree-sitter parses each file, and a language adapter extracts imports, classes and functions with line numbers.
4. Resolution. Imports are resolved to concrete files. Python needs relative imports, packages and src layouts; TS/JS needs index files, tsconfig paths and package exports. External packages become separate nodes, and dynamic imports stay unresolved instead of being guessed.
5. Graph. NetworkX computes cycles, reverse dependencies, centrality and change impact. The graph is stored in PostgreSQL per (repository, commit), so repeated analysis is served from cache.

Every edge carries provenance:

```json
{
  "source": "backend/api/routes.py",
  "target": "backend/auth/service.py",
  "type": "imports",
  "symbol": "AuthService",
  "line": 3,
  "commit": "a3f9c1e",
  "confidence": "resolved",
  "extractor": "python-adapter@0.1"
}
```

Confidence levels:

- resolved: an exact fact, the import is written in the code;
- heuristic: a likely link, for example a matching URL between frontend and backend;
- unresolved: a link probably exists but could not be determined.

On top of the graph:

- Web UI with Cytoscape.js: graph, filters, search, click-through to source lines, coverage panel.
- AI agents that answer questions with citations and highlight nodes on the graph.
- MCP server with the same graph queries for external agents.
- Report export with findings and analysis limitations.

## 4. Agents

Three roles in a LangGraph state graph. One local LLM can serve all roles.

- Explorer finds relevant files and symbols (search_symbols, read_file, find_references).
- Analyst runs graph queries and formulates claims with evidence (reverse_dependencies, impact_scope, detect_cycles, get_neighbors).
- Reviewer verifies every claim with plain code, not an LLM. It checks that the file exists in the commit, the line contains the symbol and the edge exists in the graph. A claim without enough evidence goes back to Explorer (request_revision); if the budget runs out, it is downgraded to a hypothesis.

Shared state holds the question, collected evidence, claims and a step budget (around 15 tool calls, at most 2 revisions). The final text is phrased only from verified claims. The UI streams the agent trace so the hand-offs between agents are visible.

Safety: all tools are read-only, file contents are passed to the model as clearly marked data, and instructions found in README files or comments are never followed.

Example run for "What breaks if I change AuthService?": Explorer finds the symbol and references, Analyst returns 3 direct and 5 transitive dependents and a cycle with users/models.py, Reviewer rejects "the frontend will break" because there is no TS → Python edge, Explorer finds a heuristic match on /api/login, and Reviewer downgrades the claim to a hypothesis.

## 5. Backend API

```
POST /repos                 import GitHub URL or ZIP, start analysis
GET  /repos/{id}/status     analysis progress
GET  /repos/{id}/graph      nodes and edges for Cytoscape.js
GET  /repos/{id}/file?path= source file for the viewer
POST /repos/{id}/ask        question to agents, streamed (SSE): trace steps and final answer
```

Long analysis runs as a background job with progress. The MCP server reuses the same graph functions.

Tools are plain Python functions wrapped with LangChain's @tool. The model is chosen with one config line, for example init_chat_model("ollama:qwen3:8b"), so the provider can be switched without code changes.

## 6. LLM and Ollama

Ollama is a program that downloads open-weight models and runs them locally, exposing an API at localhost:11434. Requests never leave the machine, there are no API keys and no per-request costs; the price is local hardware. Only open-weight models work (Qwen, Llama, Mistral, Gemma, DeepSeek, gpt-oss); GPT, Claude and Gemini are not available through it.

Model choice:

- Default: qwen3:8b (about 5 GB). Comfortable on a 16 GB MacBook Air M3, roughly 15–25 tokens per second.
- qwen3:14b (about 9 GB) is tight on 16 GB. Use it on machines with 32 GB.
- 32B and larger models do not fit on a 16 GB laptop.
- One agent answer takes 5–10 model calls, roughly 20–60 seconds on 8B. Streaming the agent trace makes the wait acceptable in a demo.

Important settings:

- Set num_ctx explicitly (for example 16k). The default context window is small, and longer prompts are silently truncated.
- On macOS, run Ollama natively, not in Docker. Docker on Mac has no GPU access. The backend container reaches it at http://host.docker.internal:11434.
- A fanless MacBook Air throttles under long load, so let it cool between benchmark runs.

Fallback provider: Gemini API free tier from Google AI Studio, for the demo and for the local vs cloud benchmark. On the free tier data may be used for training, which is acceptable for public repositories. Claude or OpenAI can be added later if there is a budget.

Alternatives to Ollama: LM Studio (GUI, can use MLX and be faster on Mac), MLX / mlx-lm (fastest on Apple Silicon), llama.cpp (the engine under Ollama), vLLM (GPU servers). Most expose an OpenAI-compatible API, so switching changes only the address in the config.

## 7. Language support

Detecting a language is easy, and Tree-sitter grammars exist for most languages. The hard part is resolving where each import points, because every language has its own module system:

- Go: import paths plus go.mod, strict and simple rules.
- Java and Kotlin: packages usually match folders, with Maven or Gradle modules on top.
- Python: relative imports, src layouts, namespace packages.
- TS/JS: tsconfig aliases, index files, package exports, CommonJS and ESM.
- Rust: mod tree, crates, Cargo workspaces.
- C#: namespaces are not tied to files, so a full symbol index is needed.
- C/C++: include paths come from the build system, macros and conditional compilation.
- PHP/Ruby: many links are resolved only at runtime.

Support levels:

- Level 1, full analysis: Python, TypeScript/JavaScript (MVP).
- Level 2, imports only: Go and Java if time allows, about 1–2 weeks each.
- Level 3, detected only: everything else, shown on the map and marked as not analyzed.

## 8. Competitors

- AI documentation: DeepWiki (Cognition, also has an MCP server), Google Code Wiki, GitDiagram, deepwiki-open, Swimm. The LLM generates text and diagrams, which cannot be verified.
- Code understanding for agents: Sourcegraph, Greptile, Serena (MCP over language servers), Aider repo map (Tree-sitter plus PageRank). They confirm that structural information helps LLMs, but they do not verify claims or provide a visual map for humans.
- AI PR review: CodeRabbit, Greptile, Copilot code review. They work on diffs and do not show an architecture diff.
- Classic static analysis: dependency-cruiser, madge, pydeps, import-linter, CodeScene (hotspots), SonarQube, CodeQL, NDepend. Precise graphs, but no AI explanations and no agent integration.

Each piece exists separately. Graphora combines a deterministic graph with provenance, agents with deterministic claim verification, a visual map for people and MCP for agents, all running locally.

DeepWiki describes code; Graphora computes facts about code.

## 9. Features

MVP:

- Import from a GitHub URL or ZIP, pinned to a commit.
- Language detection and a coverage report.
- Full Python and TS/JS analysis: imports, classes, functions, line numbers.
- Graph with cycles, reverse dependencies, key nodes and change impact.
- Interactive map with filters, search and source navigation.
- Three agents with citations, verification and a visible trace.
- MCP server.
- Report export.

Additional features:

- Frontend ↔ backend bridge: Python routes matched with TS HTTP calls through a heuristic edge. URL templates must be normalized, for example /users/{id} and `/users/${id}`.
- Automatic components: Louvain clustering, agent-named clusters, zoom levels system → component → file → symbol.
- Cycle breaking: minimum feedback arc set plus an agent explanation, recommendations only.
- Hotspots: change frequency from git history multiplied by graph centrality, plus bus factor (how many people have changed a file).
- GraphRAG: local embeddings for search by meaning, expanded with graph neighbours.
- AI PR check: graph diff before and after a PR compared with the PR description.
- Benchmark: 30 questions with known answers, the same model with grep vs with Graphora MCP, measuring accuracy, hallucinations, tokens and time.
- Natural-language graph queries: the LLM writes a formal query, and code executes it.
- Architecture rules in plain language, for example "UI must not access the database", checked by code.
- Onboarding tour: an agent guides through entry points to the core of the project.
- Attack surface map: paths from HTTP endpoints to eval, subprocess, raw SQL and file writes.
- Vulnerable dependency reachability: OSV.dev advisories checked against the graph.
- Tests to run: test files that transitively import a changed module.
- Dead code detection, Mermaid/C4 diagram export, permalinks to graph views, README vs code consistency check, live mode.

Recommended priority:

1. MVP plus MCP.
2. Frontend ↔ backend bridge, hotspots, onboarding tour.
3. Benchmark.
4. Architecture diff and AI PR check, shown as the roadmap.

Eleven or more features do not fit into 10–14 weeks for three people. Present it as MVP plus 2–3 features, with the rest on the roadmap.

## 10. Glossary

- MCP (Model Context Protocol): an open standard for connecting AI agents to external tools, often described as USB-C for AI. Graphora runs an MCP server, and clients like Claude Code connect to it, for example with claude mcp add graphora -- python -m graphora.mcp.
- Provenance: where an edge came from, written as file:line@commit plus a confidence level.
- Heuristic: a likely but unproven link, drawn dashed and called "likely" in answers.
- Dependency cycle: modules that depend on each other in a loop. Cycles cause circular-import errors and make modules hard to test, change or extract. The usual fix is to move the shared part into a third module or depend on an interface.
- Hotspot: a file that is changed often and has many dependents.
- Bus factor: how many people would have to leave before nobody understands a file. A value of 1 is a risk.
- Static analysis: reading code without running it.

## 11. Technical risks and pitfalls

- Import resolution is the hardest part of the project. Budget the most time for it.
- TS barrel files (index.ts with export *) collapse the graph into index files unless re-exports are followed.
- Determinism has to be enforced: Python set iteration order can change between runs, so sort nodes and edges.
- Line numbers alone are fragile evidence; store a snippet hash as well.
- Small models make tool-calling mistakes (broken JSON, unknown tools, loops). Validate arguments, retry and enforce a step budget.
- Give each agent only 3–4 tools; an 8B model handles a short tool list better.
- Trim tool output before passing it to the model.
- Prompt injection can arrive through tool output, for example a comment in a file.
- Large graphs freeze Cytoscape and become unreadable. Show folders or clusters by default and expand on click.
- The GitHub API allows 60 unauthenticated requests per hour. Download one archive or use git clone --depth 1.
- Agent tests are non-deterministic. Check that citations exist and key files are found, not exact wording.

## 12. Agree on now

1. The JSON format of the graph (nodes, edges, provenance), so frontend and backend can work in parallel from week one.
2. Two or three small test repositories with known imports, cycles and frontend ↔ backend links. They are the ground truth for acceptance tests and the benchmark.
3. Model qwen3:8b with an explicit num_ctx.
4. Sorted output everywhere, for determinism.
5. A fixed MVP feature list.

## 13. Team

- Developer 1: Python backend, repository import, security.
- Developer 2: Tree-sitter adapters, graph model, NetworkX, test repositories.
- Developer 3: React, Cytoscape.js, analysis UI, evidence display.
- Together: multi-agent design, LangGraph tools, integration tests, Docker, demo.

Order of work: import → adapters and graph → UI → agents → verification → tests and demo.

## 14. Pitch

Structure:

1. Hook: agents write code faster than we can understand it.
2. Shift: the bottleneck is understanding and review, not writing.
3. Why chat agents are not enough: one-off, non-reproducible, unverifiable answers.
4. Solution: graph as the source of truth, agents with verification, MCP for external agents.
5. Demo: question → highlighted graph → answer with file:line → Reviewer rejecting an unproven claim.
6. MVP, team, plan.
7. Close with the tagline.

Delivery tips:

- If time is short, show three things: the provenance card (evidence), the hypothesis (honesty) and the agent trace (agents checking each other).
- Say that the screens are a UI concept, not a finished product.
- Keep terms like adapter, provenance and NetworkX for the Q&A.
- Split the talk between team members by their areas.
- Pre-analyze the demo repository and keep a recorded video in case the model hangs.

Answers to hard questions are in vision-en.md and vision-pl.md.

## 15. Housekeeping

- Mockup data (repository names, files, numbers) is illustrative. The numbers on the MCP screen are benchmark targets, not results.
- Check that the name Graphora is not taken by a similar product.
- Do not publish the images of other student projects from the original specification without checking rights.
- Add a LICENSE file (for example MIT).
