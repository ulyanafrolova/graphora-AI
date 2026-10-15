# Graphora — UI Concept

> These screens are UI mockups of the planned product. Repository names, files and numbers are illustrative.

---

## 1. Import

![Import](01-import.png)

The user pastes a public GitHub URL or uploads a ZIP. Graphora pins the analysis to a single commit (`a3f9c1e`), so the same commit always produces the same graph.

- **Safety limits:** max size, file count and time budget; `node_modules`, `venv` and minified files are skipped; ZIPs are protected against path traversal and zip bombs. Analyzed code is **never executed**.
- **Analysis progress:** snapshot → language detection → Tree-sitter parsing → import resolution → graph building.
- **Language coverage:** Python and TS/JS get full analysis, while Go is marked *detected only*. Graphora never claims analysis it didn't do.

---

## 2. Dependency graph

![Dependency graph](02-graph.png)

The system-level view of the repository. Files are grouped into components with Louvain community detection, and an agent suggests component names (*Auth*, *Billing*, …).

- Edge width = number of imports between components.
- The **yellow dashed edge** is the cross-language bridge: 23 HTTP routes connect the TypeScript frontend to the Python API. It is marked *heuristic* because it is matched by URL, not by a static import.
- The **red edge** is a dependency cycle between *Auth* and *Users*.
- The side panel shows component details: dependencies, dependents, centrality rank and key files.
- Zoom levels: System → Component → File → Symbol.

---

## 3. Large repository: overview

![Large graph overview](11-large-graph-overview.png)

How Graphora keeps a 4 800-file repository readable:

- **Clustering:** each dot is a file, its color is the component, and its size is the number of dependents.
- **Edge bundling:** thousands of edges between components are drawn as bundles instead of a hairball. Red bundles contain cycles.
- **Hotspots:** the glowing red dots are the riskiest files (frequent changes × high centrality).
- Labels and details appear progressively as you zoom in.

---

## 4. Large repository: zoom into a component

![Large graph zoom](12-large-graph-zoom.png)

The *Auth* component is expanded to file level, while neighbouring components are collapsed into dashed nodes that show how many edges lead to them.

- **Impact mode:** `service.py` is selected, and blue edges show what a change would affect. The panel summarises it: **214 files across 7 components**, broken down by component.
- The Frontend impact is shown as *~37 heuristic*: it is likely but not statically proven.
- The **minimap** shows where the current view sits in the whole repository.

---

## 5. Code & provenance

![Code and provenance](03-code-provenance.png)

Every edge in the graph is backed by a concrete line of code.

- Line 3 (`from ..auth.service import AuthService`) is the evidence for the edge `routes.py → auth/service.py`.
- **Provenance card:** source `routes.py:3@a3f9c1e`, confidence `resolved`, extractor version and a snippet hash (so the evidence survives line shifts).
- Gutter markers distinguish resolved imports, external packages, HTTP routes and call references.
- **Incoming edges:** `frontend/api/auth.ts` is linked as *heuristic* via `fetch("/api/login")` ↔ `@router.post("/login")`.

---

## 6. Ask agents

![Ask agents](04-ask-agents.png)

The user asks: *“What breaks if I change AuthService?”*

- The answer lists **3 direct and 5 transitive dependents**, and every claim carries a verified `file:line@commit` citation.
- The **cycle** with `users/models.py` is reported as a verified fact.
- The claim that the frontend is affected is shown as a **hypothesis**, because it cannot be proven statically.
- The relevant nodes are highlighted on the graph on the right.
- The run took 9 tool calls with a local `qwen3:8b` model.

---

## 7. Agent trace

![Agent trace](05-agent-trace.png)

A transparent log of the LangGraph run behind the answer above.

- **Explorer** finds the symbol and its references, and **Analyst** runs graph queries (`reverse_dependencies`, `impact_scope`, `detect_cycles`).
- **Reviewer** checks every claim with deterministic code, not an LLM. Here it **rejects** “Frontend will break” because no TS → Python edge exists and sends the task back (`request_revision`).
- Explorer searches again and finds a heuristic HTTP match, so Reviewer **downgrades** the claim to a hypothesis.
- Claim statuses and the step budget (9/15 tool calls, 1/2 revisions) are shown on the right. All tools are read-only.

---

## 8. Cycles

![Cycles](06-cycles.png)

All circular dependencies found with graph algorithms.

- **Before:** `auth/service.py ⇄ users/models.py`.
- **Edge to remove:** computed as a minimum feedback arc set. It points to `users/models.py:8`, which imports only `hash_pw`.
- **After (suggested):** move `hash_pw` into `common/user_lookup.py`, so both modules depend on a shared layer instead of each other.
- This is a recommendation only: Graphora never modifies code.

---

## 9. Hotspots

![Hotspots](07-hotspots.png)

Risk = change frequency (git history, 90 days) × centrality in the graph. Tile size = lines of code.

- `auth/service.py` is the top risk: 47 commits, 12 dependents, and a **bus factor of 1** (only one person changed it).
- `ui/store/index.ts` also has a bus factor of 1, with 14 dependents.
- The analyst summary links the hotspot back to the *auth ⇄ users* cycle.

---

## 10. PR impact

![PR impact](08-pr-impact.png)

Checks a pull request written by an AI agent: **intent vs. reality**.

- The PR description claims *“Only changes the login logic in `auth/`”*.
- The graph diff (`a3f9c1e → 7d20b5a`) shows otherwise: a new dependency on `billing`, a **new cycle** auth → billing → auth, and a direct `api → db` import.
- **Architecture rule** *“API must not access the database directly”* is violated at `api/routes.py:6`.
- **Tests to run:** only 7 of 300 test files are affected by the change.

---

## 11. Security

![Security](09-security.png)

- **Attack surface:** paths from HTTP entry points to dangerous sinks. `POST /upload` reaches `os.system()` in 3 calls, and `GET /reports` reaches a raw SQL f-string. `POST /login` reaches no dangerous sinks.
- **Dependency reachability:** 12 packages have known vulnerabilities (OSV.dev), but the graph shows that **only 2 are actually reachable** from the code.
- **Prompt-injection guard:** instruction-like text found in `README.md` is treated as data, not executed by the agents.

---

## 12. MCP for coding agents

![MCP](10-mcp.png)

Graphora exposes its graph queries as an MCP server, so external coding agents (Claude Code, Cursor, …) can use them.

- Connect with one command, e.g. `claude mcp add graphora -- python -m graphora.mcp`.
- **Exposed read-only tools:** `reverse_dependencies`, `impact_scope`, `detect_cycles`, `get_neighbors`, `tests_for`, `verify_evidence`.
- In the terminal example, the agent answers *“What could break if I rewrite AuthService?”* with two tool calls instead of grepping the repository, and gets direct and transitive dependents, the cycle, a hypothesis and the tests to run.
- The numbers *1 vs ~14 tool calls* and *−80% context tokens* are **targets** to be measured in our benchmark.
