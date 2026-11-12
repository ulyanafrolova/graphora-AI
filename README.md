## Vision

AI agents now write code faster than humans can understand it.
The bottleneck is no longer writing code — it's knowing what it actually does.

**Graphora** builds a static, commit-pinned dependency graph with provenance on every edge (`file:line@commit`, confidence level).
Cycles, reverse dependencies and change impact are computed algorithmically, not inferred by a model.
Collaborating AI agents answer questions on top of it, and a deterministic verifier
downgrades any claim not backed by the graph to a hypothesis.

We don't compete with coding agents — we give them a map.
Via MCP, Claude Code, Cursor and others get transitive dependency answers in one tool call instead of grepping through the repo.

> AI agents generate answers. Graphora gives them — and you — facts.
  
<br>
<details>

<summary><b>Demo</b></summary>

<br>

![Import](docs/demo/01-import.png)

Import a public GitHub repository or ZIP, pinned to one commit. Code is never executed.

![Large graph overview](docs/demo/11-large-graph-overview.png)

The whole repository as one map: files grouped into components, edges bundled, hotspots highlighted.

![Large graph zoom](docs/demo/12-large-graph-zoom.png)

Zoom into a component to see what a change to one file would affect.

![Hotspots](docs/demo/07-hotspots.png)

Risky files: frequently changed and heavily depended on.

More screens in [docs/demo](docs/demo).

</details>

## Status

Done and merged into `main` (features 001–006, graph schema v3):

| # | Feature | What it gives |
|---|---|---|
| 001 | Python graph CLI | `graphora analyze <dir>`: file nodes, import edges with provenance, coverage report, deterministic JSON |
| 002 | Repository ingest | Analyze a public GitHub URL (pinned to a commit) or a ZIP; safe extraction, size and time limits |
| 003 | TS/JS analysis | ESM, CommonJS, dynamic imports, `tsconfig` paths, monorepo workspaces, re-exports |
| 004 | Graph queries | dependencies, dependents, impact, neighbors, cycles, key files (`graphora query`) |
| 005 | Storage and HTTP API | PostgreSQL store per (repository, snapshot), read-only API (`graphora serve`) |
| 006 | MCP server | Read-only graph tools for coding agents over stdio (`graphora mcp`), from a graph file or the store |

In progress (PR #22, issue #19, graph schema v5):

| # | Feature | What it gives |
|---|---|---|
| 007 | C# analysis, slice 1 | `using` → namespace → declaring files, `.csproj` project and package references read as data, `dotnet`/`nuget` externals, `bin`/`obj` skipped next to a `.csproj` |
| 008 | C# analysis, slice 2 | Type references give exact file → file edges; `global using`, implicit usings, `<Using>` items and `Directory.Build.props`; unresolved type names counted per file |

Next on the roadmap: end-to-end pipeline, claim verifier and agents, `/ask` with
streaming, hotspots, web UI, frontend ↔ backend bridge, benchmark.

## Architecture

```mermaid
flowchart LR
    src["Local folder<br/>GitHub URL + ref<br/>ZIP archive"]

    subgraph analyze["Analysis (once per snapshot, no LLM, code never executed)"]
        ingest["ingest/<br/>fetch, safe extract,<br/>walk + skip rules, limits"]
        detect["detect/<br/>language by extension<br/>and marker files"]
        adapters["adapters/<br/>Tree-sitter: imports,<br/>definitions, exports"]
        resolve["resolve/<br/>Python packages, src layout<br/>TS/JS index, tsconfig, workspaces<br/>C# namespace index, .csproj"]
        build["graph/build<br/>nodes, edges, provenance,<br/>coverage, sorted output"]
        ingest --> detect --> adapters --> resolve --> build
    end

    src --> ingest
    build --> json[("graph.json<br/>schema v5")]
    build --> store[("store/<br/>PostgreSQL")]

    json --> queries["graph/queries<br/>NetworkX"]
    queries --> cli["graphora query"]
    store --> api["api/<br/>read-only HTTP"]

    subgraph next["Planned"]
        mcp["mcp/ server"]
        agents["agents/ Explorer, Analyst, Reviewer"]
        verify["verify/ deterministic claim check"]
        ui["frontend/ React + Cytoscape.js"]
    end

    queries -.-> mcp
    queries -.-> agents
    agents -.-> verify
    api -.-> ui
```

All graph questions are answered by code in `backend/src/graphora/graph/`; the CLI, API and (later) MCP
server and agents only call it. The LLM will only phrase claims that the verifier has checked against the
graph.

### Modules

| Folder | Role |
|---|---|
| `ingest/` | Source resolution (`source.py`), GitHub archive download (`github.py`, `fetch.py`), safe ZIP extraction (`archive.py`), file walk and skip rules (`walk.py`), snapshot id (`snapshot.py`) |
| `detect/` | Language and status per file: `analyzed`, `detected_only`, `not_code` |
| `adapters/` | Tree-sitter extractors for Python, JS/TS and C#: import sites, definitions, exports, line and column; `.csproj` files read as XML data (`msbuild/`) |
| `resolve/` | Import target resolution; never guesses — an unknown target becomes an `unresolved` node |
| `graph/` | Model, build, canonical serialization, loading and all queries |
| `store/` | PostgreSQL store: analyses, deduplicated file blobs |
| `api/` | FastAPI router, read-only |
| `cli/` | `analyze`, `query`, `serve` |

## Graph schema

The contract between backend and frontend is [schema/graph.schema.json](schema/graph.schema.json)
(`schema_version: 5`). One document per snapshot:

```mermaid
erDiagram
    DOCUMENT ||--|| SNAPSHOT : "pinned to"
    DOCUMENT ||--o{ NODE : nodes
    DOCUMENT ||--o{ EDGE : edges
    DOCUMENT ||--|| COVERAGE : coverage
    EDGE }o--|| NODE : source
    EDGE }o--|| NODE : target
    NODE ||--o{ DEFINITION : "file: definitions"
    NODE ||--o{ EXPORT : "file: exports"
    COVERAGE ||--o{ COVERAGE_FILE : files
    COVERAGE ||--o{ SKIPPED : skipped

    DOCUMENT {
        int schema_version "5"
        string snapshot
        map extractors "name -> semver"
    }
    SNAPSHOT {
        string id "commit sha | sha+dirty:hash | content:hash"
    }
    NODE {
        string id
        enum kind "file | external | unresolved | asset | project"
        string path "file, asset, project"
        enum language "python | typescript | javascript | csharp"
        string project "C# file: owning project"
        string name "external"
        enum ecosystem "python | npm | dotnet | nuget"
        enum category "stdlib | builtin | third_party"
        string reference "unresolved"
    }
    EDGE {
        string id
        enum type "imports | reexports | project_reference | package_reference | type_reference"
        enum form "static | dynamic | require"
        enum directive "C#: using | using_static | using_alias"
        bool global_using
        bool type_only
        string symbol
        string alias
        int line
        int column
        string snapshot
        enum confidence "resolved | heuristic | unresolved"
        enum reason "not_found | dynamic | namespace_spread | ..."
        string extractor "name@version"
        string snippet_hash
    }
    DEFINITION {
        string kind
        string name
        int line
        string exported_as
    }
    EXPORT {
        string name
        string local
        int line
    }
    COVERAGE_FILE {
        string path
        string language
        enum status "analyzed | detected_only | not_code"
        list flags
        int unresolved_type_names "C# only"
    }
    SKIPPED {
        string path
        enum reason "excluded_dir | nested_repository | symlink | minified | unreadable_dir"
    }
```

Every edge carries its provenance: `file:line@snapshot`, a confidence level, the extractor version and a
hash of the source snippet. Output is byte-for-byte deterministic: everything is sorted, there are no
timestamps.

### Store schema

```mermaid
erDiagram
    ANALYSES ||--o{ FILES : "repository, snapshot"
    FILES }o--o| BLOBS : sha256

    ANALYSES {
        text repository PK
        text snapshot PK
        int schema_version
        text extractors "canonical JSON"
        text warnings "canonical JSON"
        bytea graph "graph document, byte for byte"
        text graph_sha256
    }
    FILES {
        text repository PK
        text snapshot PK
        text path PK
        bool has_text
        int line_count
        bigint size
        text sha256 FK
    }
    BLOBS {
        text sha256 PK
        bytea content
    }
```

File contents are stored once per hash, so re-analyzing a commit or a similar commit reuses blobs.

## Quick start

Requires [uv](https://docs.astral.sh/uv/). Python, TypeScript/JavaScript and C# projects are fully analyzed
(C# without a .NET SDK: `.csproj` files are read as data); other languages are detected and listed in the
coverage report.

```
cd backend && uv sync
uv run graphora analyze path/to/project --out graph.json
uv run graphora analyze https://github.com/<owner>/<repo> --ref <ref> --out graph.json
uv run graphora analyze project.zip --out graph.json
```

Ask questions about a graph:

```
uv run graphora query graph.json dependents src/app/auth.py
uv run graphora query graph.json impact src/app/auth.py --max-depth 3 --follow-barrels
uv run graphora query graph.json cycles
uv run graphora query graph.json key-files --format json
```

Questions: `dependencies`, `dependents`, `impact`, `neighbors`, `cycles`, `key-files`.

### Store and HTTP API

```
make db                                   # PostgreSQL 17 in docker compose
export GRAPHORA_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora
uv run graphora analyze <source> --store  # save, or reuse a stored analysis
uv run graphora serve                     # http://127.0.0.1:8000
```

| Endpoint | Returns |
|---|---|
| `GET /api/v1/repositories` | Stored repositories and their snapshots |
| `GET /api/v1/graph?repository=&snapshot=` | The graph document, as stored |
| `GET /api/v1/file?repository=&snapshot=&path=[&start=&end=]` | Source lines for the viewer |

### Tests

```
uv run pytest -m "not db"   # without PostgreSQL
uv run pytest               # all, needs GRAPHORA_TEST_DATABASE_URL
```

Golden fixtures in [fixtures/repos/](fixtures/repos) (`py-*`, `ts-*`, `js-commonjs`, `mixed-fullstack`)
have hand-written `expected.json` files as ground truth.

## Authors

This project was completed as part of the AI Agents class at Warsaw University of Technology.

© Anna Granos, Ulyana Frolova, 2026

## License

Released under the [MIT License](LICENSE).
