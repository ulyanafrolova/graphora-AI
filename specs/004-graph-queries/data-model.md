# Data Model: Graph Queries

The graph document and `schema/graph.schema.json` do **not** change (schema v2 stays). Input types are the
existing ones in `backend/src/graphora/graph/model.py`. This file describes the in-memory index and the answer
types in `graph/results.py`. Research references: [research.md](research.md).

## Input

| Type | Source | Notes |
|---|---|---|
| `GraphDocument` | `graph/load.py: loads(bytes)` | validated (R2); raises `InvalidGraph` |

## GraphIndex (built once per document, `graph/queries.py`)

| Field | Meaning |
|---|---|
| `doc` | the `GraphDocument` |
| `nodes` | node id → node |
| `links` | NetworkX `DiGraph` over node ids; each graph edge has attribute `edges: tuple[Edge, ...]` (sorted by `edge_sort_key`, R3) |
| `runtime_links` | the same graph without type-only edges (built lazily) |
| `unresolved` | file id → its `unresolved` edges, sorted |
| `completeness` | `Completeness` (R9) |

Built by `index(doc)`. Nodes and links are inserted in sorted id order. Immutable after construction; safe to
share between queries.

## Answer types (`graph/results.py`)

All are frozen dataclasses. `to_dict()` gives the JSON shape in
[contracts/answers.md](contracts/answers.md); `dumps(answer) -> bytes` is canonical (R11).

### Link

| Field | Type | Meaning |
|---|---|---|
| `source` | `str` | node id |
| `target` | `str` | node id |
| `edges` | `tuple[Edge, ...]` | every edge between them, sorted; never empty |
| `confidence` | `"resolved" \| "heuristic"` | strongest among `edges` (R4) |
| `type_only` | `bool` | true when every edge is type-only |
| `via` | `tuple[Edge, ...]` | barrel chain only: the re-export edges after the import edge, in order; empty otherwise |

A link with `via` is a derived (barrel) link: `edges` holds the import edge(s) into the barrel and `target` is
the defining file. It is never written to the graph.

### Item

| Field | Type | Used by |
|---|---|---|
| `node` | `str` | all — the dependent, dependency or key file |
| `kind` | `"file" \| "external" \| "asset"` | all |
| `distance` | `int \| None` | impact (≥ 1) |
| `chain` | `tuple[Link, ...]` | dependents (one link), dependencies (one link), impact (from `node` to the target, `distance` links) |
| `confidence` | `"resolved" \| "heuristic"` | weakest link in `chain` |
| `type_only` | `bool` | any link in `chain` is type-only |
| `transitive_dependents` / `direct_dependents` | `int \| None` | key files only |

### UnresolvedImport

| Field | Type |
|---|---|
| `edge` | `Edge` (confidence `unresolved`, has `reason`) |

### CycleGroup

| Field | Type | Meaning |
|---|---|---|
| `files` | `tuple[str, ...]` | sorted file ids |
| `cycle` | `tuple[Link, ...]` | example cycle starting and ending at `files[0]` (R6) |
| `type_only` | `bool` | no cycle remains without type-only edges |
| `confidence` | `"resolved" \| "heuristic"` | weakest link in `cycle` |

### Completeness

| Field | Type |
|---|---|
| `unresolved_imports` | `int` |
| `not_analyzed_files` | `int` |
| `files_with_errors` | `int` |

### Answer

| Field | Type | Meaning |
|---|---|---|
| `snapshot` | `str` | the document's snapshot id (FR-017) |
| `question` | `"dependencies" \| "dependents" \| "impact" \| "neighbors" \| "cycles" \| "key_files"` | |
| `target` | `str \| None` | resolved node id; `None` for cycles and key files |
| `options` | `dict[str, object]` | every option with its effective value, including defaults |
| `items` | `tuple[Item, ...]` | dependencies, dependents, impact, key files |
| `incoming` / `outgoing` | `tuple[Item, ...]` | neighbors only |
| `unresolved` | `tuple[UnresolvedImport, ...]` | dependencies and neighbors only |
| `groups` | `tuple[CycleGroup, ...]` | cycles only |
| `total` | `int` | number of items (or groups) before the limit |
| `truncated` | `bool` | `total > limit` |
| `cut` | `bool` | impact only: `max_depth` stopped the search before it ended |
| `completeness` | `Completeness \| None` | all except cycles |

## Ordering rules (FR-015)

| List | Order |
|---|---|
| dependencies, outgoing | target id |
| dependents, incoming | source id |
| impact items | distance, node id |
| key files | −transitive, −direct, node id |
| cycle groups | first file id |
| `edges` inside a link | `edge_sort_key` (source, line, column, target, symbol, alias, type) |
| `unresolved` | `edge_sort_key` |
| `options` keys, all dict keys | sorted by the canonical JSON writer |

The limit is applied after sorting. For neighbors it applies to `incoming` and `outgoing` separately;
`total` is the sum of both full lists and `truncated` is true if either list was cut.

## Errors

| Error | When | CLI exit code |
|---|---|---|
| `InvalidGraph(message)` | `loads` fails (R2) | 7 |
| `NodeNotFound(target, status)` | target does not resolve (R10); `status` is `detected_only`, `not_code`, a skip reason, `ambiguous`, `invalid_path` (backslash, absolute or `..`) or `not_in_snapshot` | 8 |
| `ValueError` | bad option value (negative limit, `max_depth < 1`) | 2 |
