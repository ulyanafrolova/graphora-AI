# Contract: UI routes, screens and data sources

All routes are client routes of one page; the service returns `index.html` for them (backend.md § Serving the UI).

## Routes

| Route | Screen (docs/demo) | Data |
|---|---|---|
| `/` | redirect: last opened snapshot, else `/import` | `/repositories` |
| `/import` | Import (§ 1) | `POST /jobs`, `POST /jobs/zip`, `GET /jobs/{id}`, `/info` (limits) |
| `/r/:repo/:snap/graph?level&component&node&impact&hide` | Dependency graph (§ 2–4) | `/graph`, `/components`, `/key_files?limit=500`, `/cycles?limit=500`, `/hotspots?limit=500`, `/impact`, `/neighbors`, `/files` |
| `/r/:repo/:snap/code?path&line` | Code & provenance (§ 5) | `/graph`, `/file`, `/dependencies`, `/dependents` |
| `/r/:repo/:snap/ask` | Ask agents (§ 6) | `POST /ask` (SSE), history (IndexedDB) |
| `/r/:repo/:snap/trace?run` | Agent trace (§ 7) | history (IndexedDB) |
| `/r/:repo/:snap/cycles?group` | Cycles (§ 8) | `/cycles?limit=500`, `/file` for cut lines |
| `/r/:repo/:snap/hotspots` | Hotspots (§ 9) | `/hotspots?limit=500`, `/files` |
| `/r/:repo/:snap/pr-impact`, `/security` | placeholders (§ 10, § 11) | none |
| `/r/:repo/:snap/mcp` | MCP for agents (§ 12) | `/info` |

`:repo` and `:snap` are URL-encoded; unknown values show the "not found" state with a link to `/import`.

## Shell

- Header: product name; `repository @ short commit` (first 7 characters of a SHA, or `content:` id shortened) as a
  snapshot picker; one badge per language of `overview.languages` coloured by its coverage status (analyzed → green,
  detected only → grey); model badge from `/info` (`<model> · local` for `ollama:`, `agents off` when disabled).
- Sidebar: Project (Import, Dependency graph, Code & provenance), AI agents (Ask agents, Agent trace), Insights
  (Cycles, Hotspots, PR impact, Security), Integrations (MCP for agents); footer "Code is never executed. Read-only
  agents."

## Visual language (shared legend)

| Meaning | Style |
|---|---|
| resolved link | solid, neutral or component colour |
| heuristic link | dashed, amber, label "heuristic" |
| unresolved import | grey hollow marker, never drawn as a link to a file |
| cycle link | red |
| impact path | blue |
| hypothesis (agents) | amber box, "Hypothesis — not statically proven" |
| verified fact | green check, citation `file:line @ short commit` |
| external package | grey pill "external" |

## Error and empty states

| Service answer | UI |
|---|---|
| network error / 503 `store_unavailable` | "Graphora service unavailable" + Retry |
| 404 repository/snapshot | "Snapshot not found" + link to Import |
| 409 `stale` | "Analyzed with an older version — analyze again" + Import prefilled when the source is known |
| 429 `busy` (ask) | "Another question is being answered" + Retry after `Retry-After` |
| 503 `model_unavailable` | "Model not available" + how to start Ollama |
| 429 `too_many_jobs` | "Too many analyses queued, try later" |
| job `failed` | the failure kind and message in plain words + Try again |
| empty lists | explicit "no cycles", "no definitions", "history not available (reason)" |
