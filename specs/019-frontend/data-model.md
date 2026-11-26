# Data Model: Web UI

No graph schema change and no store schema change. New answer types in the query layer, two small HTTP documents, and
client-side state.

## Backend answer types (`graph/results.py`)

### Component

| Field | Type | Rule |
|---|---|---|
| `id` | str | `component:<n>`, 1-based in component order |
| `name` | str | research R3 naming rule; unique within the answer |
| `files` | list[str] | file node ids, sorted |
| `file_count` | int | `len(files)` |
| `has_cycle` | bool | a cycle group lies inside the component |

### ComponentLink

| Field | Type | Rule |
|---|---|---|
| `source`, `target` | str | component ids, `source != target` |
| `imports` | int | number of file links from source files to target files (≥ 1) |
| `heuristic` | int | how many of those are heuristic (0 ≤ heuristic ≤ imports) |
| `in_cycle` | bool | some cycle group has files in both components |

### Components answer

`Answer` with `question: "components"`, `target: null`, `options: {"include_type_only"}`, `components: [Component]`
(component order), `links: [ComponentLink]` (sorted by source, target), `total` = number of components,
`truncated: false`, `completeness`.

### CycleCut (new field `cut` of `CycleGroup`)

| Field | Type | Rule |
|---|---|---|
| `method` | `"exact"` \| `"greedy"` | exact only for groups of ≤ 20 files whose search finished within budget |
| `links` | list[Link] | the suggested links to remove, sorted by (source, target); each Link carries its edges (file, line, imported name) |

Rule: removing all `links` leaves the group without cycles (checked in tests).

## HTTP documents

- **Files** (`GET /api/v1/files`): `{"repository", "snapshot", "files": [{"path", "has_text", "line_count"}]}` sorted by
  path.
- **Info** (`GET /api/v1/info`): `{"version", "ask": {"enabled", "model"}, "jobs": {"enabled"}, "mcp_tools": [{"name",
  "description"}]}`.

## Client state (frontend)

### Route state (in the address, research R1)

| Field | Values |
|---|---|
| `repository`, `snapshot` | stored names |
| `screen` | `import`, `graph`, `code`, `ask`, `trace`, `cycles`, `hotspots`, `pr-impact`, `security`, `mcp` |
| `level` | `system` (default), `component`, `file` |
| `component` | component id when `level=component` |
| `node` | selected node id |
| `impact` | `on` when impact mode is on |
| `hide` | `tests`, `external` (any combination) |
| `path`, `line` | code view file and selected line |

### Server state (cached per repository and snapshot)

Graph document, overview, components, key files, hotspots, cycles, line counts, info, and per-node answers (impact,
neighbors, dependencies, dependents, definitions). Invalidated when the snapshot changes; never merged across
snapshots.

### Import job (view of `GET /api/v1/jobs/{id}`)

`stage`: `queued` → `resolving` → `fetching` → `analyzing` → `storing` → `done` | `failed`. Polled every 1 s until
`done` or `failed`; `done` carries repository and snapshot, `failed` an error kind and message.

### Agent run

| Field | Rule |
|---|---|
| `question` | text as typed |
| `steps` | `step` events in order (`n` = 1, 2, …) |
| `answer` | the `answer` event document (answer + trace) |
| `status` | `streaming` → `done` \| `error` |
| `created` | client time, used only for ordering the history |

### Answer history (IndexedDB, research R10)

Key `[repository, snapshot, created]`; at most 20 per (repository, snapshot), oldest dropped first; "clear history"
deletes a snapshot's entries.
