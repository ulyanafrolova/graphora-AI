# Data Model: Claim Verifier and Agent Tools

Types in `graphora/verify/claims.py` and `graphora/tools/`. All are frozen; `to_dict` drops fields that are
`None`; JSON is written with sorted keys (as `graph/results.py`). Research references: [research.md](research.md).

## Step

One import link a claim relies on (R3, R5).

| Field | Type | Rule |
|---|---|---|
| `path` | str | repository-relative path of the source: a file, or a `.csproj` / `.sln` for project, package and solution edges |
| `line` | int | ≥ 1, the import line |
| `target` | str | anything `queries.resolve` accepts: path, node id, package name |
| `name` | str \| None | imported name; checked with `queries.matches_symbol` when set |

## Claim

| Field | Type | Used by kinds |
|---|---|---|
| `kind` | `dependency \| chain \| definition \| mention \| query` | all |
| `statement` | str | all; carried along, never read by the verifier |
| `snapshot` | str | all; must equal the checked snapshot |
| `steps` | tuple[Step, ...] | dependency (exactly 1), chain (≥ 2, `steps[i].target` resolves to the file of `steps[i+1].path`) |
| `path`, `line`, `symbol` | str, int, str | definition, mention |
| `question` | `dependencies \| dependents \| impact \| neighbors \| cycles \| key_files` | query |
| `target` | str \| None | query; None only for `cycles` and `key_files` |
| `options` | dict | query; allowed keys per question: `include_type_only`, `follow_barrels`, `symbol` (dependents), `max_depth` (impact), `level` (dependencies, dependents, impact, cycles) |
| `count` | int \| None | query; exactly one of `count`, `member`, `rank` |
| `member` | str \| None | query; a node the result contains (path or id) |
| `distance` | int \| None | query with `member`, impact only |
| `rank` | int \| None | query, `key_files` only: the member is within the first `rank` files |

A dependency or chain claim without steps, or a definition or mention claim without a path, is rejected with
`no_citation` before validation. Validation (any other failure → `invalid_claim`): known kind; fields of other kinds absent; lines ≥ 1; symbol, path
and target non-empty; chain steps connected; option keys allowed for the question; exactly one query assertion.

`Claim.cite()` gives the display form `path:line@snapshot` (first step for chains).

## Verdict

| Field | Type | Rule |
|---|---|---|
| `status` | `verified \| heuristic \| rejected` | |
| `fact` | bool | `status == "verified"` (FR-005) |
| `checks` | tuple[Check, ...] | in the order run; stops at the first failed check |
| `reason` | Reason \| None | set exactly when rejected |
| `hint` | str \| None | the correct line, names, count, distance or rank when known |
| `step` | int \| None | 1-based failing step of a chain |
| `proof` | tuple[Edge \| Line, ...] | edges with full provenance (sorted by `edge_sort_key`) and/or stored lines |

`Check`: `name` (`snapshot`, `claim`, `source`, `target`, `edge`, `line`, `name`, `file`, `text`, `range`,
`symbol`, `definition`, `query`), `ok` (bool), `detail` (short fixed-format text).

`Line`: `path`, `n`, `text` (the stored line, unchanged).

### Reasons

| Reason | When |
|---|---|
| `invalid_claim` | validation failed |
| `no_citation` | a dependency/chain claim without steps, or definition/mention without path |
| `snapshot_mismatch` | claim snapshot ≠ checked snapshot |
| `file_not_in_snapshot` | path not in the graph's coverage |
| `file_not_analyzed` | dependency source is `detected_only`, `not_code` or skipped |
| `target_not_found` | `queries.resolve` failed for the target (its message is the hint) |
| `no_edge` | no resolved or heuristic edge from source to target |
| `import_unresolved` | no edge to the target, but an unresolved import on the cited line |
| `edge_not_on_line` | edges exist, none on the cited line (hint: their lines) |
| `name_not_imported` | edges on the line, none for the name (hint: imported names) |
| `text_unavailable` | no text source, or the stored file has no text |
| `line_out_of_range` | line > line count |
| `symbol_not_on_line` | the name is not a whole name on the line (hint: definition or nearest line) |
| `definition_not_in_graph` | no definition with the name in the file |
| `count_mismatch` | count ≠ total (hint: actual total) |
| `not_in_result` | member not in the result or at another distance (hint: actual distance) |
| `rank_mismatch` | member beyond `rank` or not ranked (hint: actual position) |

### Status rules

- dependency: `verified` if a remaining edge is resolved, else `heuristic`.
- chain: weakest step; first rejected step rejects the chain.
- definition, mention: `verified` or `rejected` (text has no confidence).
- query count: `heuristic` if any counted item is heuristic; member: the item's confidence; rank:
  `heuristic` if any item of `impact(member)` is heuristic.

## TextSource

Protocol `get(path) -> FileText | None` (`store.FileText`). `store_text(store, repository, snapshot)` reads
whole files through `Store.get_file` and caches them for one `verify` call.

## ToolSpec, ToolResult, LineRef

| Type | Fields |
|---|---|
| `ToolSpec` | `name`, `description` (fixed text) |
| `ToolResult` | `text` (for the model, ≤ `MAX_CHARS`), `citations` (tuple[Claim, ...]), `lines` (LineRef \| None), `cut` (bool), `next` (int \| None: next offset or start line), `error` (str \| None) |
| `LineRef` | `path`, `start`, `end`, `snapshot` |

With `error` set, `text` is the error message and the other fields are empty.

Limits (`tools/limits.py`): `MAX_ITEMS = 20`, `MAX_LINES = 60`, `MAX_CHARS = 4000`.
