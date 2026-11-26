# Data Model: Hotspots

The types added by 014. JSON shapes are in contracts/graph-schema-v8.md and contracts/interfaces.md.

## History (graph model, `graph/model.py`)

One per graph document: what the git history of the snapshot commit says, as counts.

| Field | Type | Meaning |
|---|---|---|
| `status` | `available` \| `partial` \| `not_available` | `partial` = cut by the time limit (research R7) |
| `reason` | `HistoryReason` \| None | why history is not available; None unless `not_available` |
| `commit` | 40-hex SHA \| None | the commit the history starts from (the SHA part of the snapshot id) |
| `window_start` | UTC timestamp text \| None | commit time of `commit` minus 365 days |
| `newest`, `oldest` | UTC timestamp text \| None | commit dates of the newest and oldest counted commit |
| `commits_read` | int ≥ 0 | non-merge commits counted |
| `merges_skipped` | int ≥ 0 | merge commits walked but not counted |
| `shallow_skipped` | int ≥ 0 | commits not counted because their parents are missing |
| `local_changes` | bool | true for a `+dirty` snapshot: uncommitted changes are not counted |
| `files` | tuple of `FileHistory` | sorted by path; only file nodes with at least one counted commit |

`HistoryReason`: `no_git`, `zip`, `unreadable`, `skipped`, `fetch_failed`, `too_large`, `time_limit`,
`not_collected`.

Rules (checked by `History.__post_init__` and by `load.py`):

- `available` and `partial`:
  - `reason` is None, `commit` and `window_start` are set;
  - `newest` and `oldest` are set exactly when `commits_read > 0`;
  - `partial` needs `commits_read > 0` (zero commits read under the time limit is `not_available: time_limit`).
- `not_available`:
  - `reason` is set;
  - `commit`, `window_start`, `newest` and `oldest` are None;
  - every count is 0, `files` is empty and `local_changes` is false.
- `files`:
  - paths are unique and sorted;
  - each entry has `commits ≥ 1` and `1 ≤ authors ≤ commits`.
- Final or retryable (research R6): `available` and `not_available` with `no_git`, `zip` or `unreadable` are
  final; everything else is retryable. `History.final` is a property, not a stored field.

The default for documents built outside the CLI and the pipeline is `NOT_COLLECTED = History("not_available",
"not_collected", …)`.

## FileHistory

| Field | Type | Meaning |
|---|---|---|
| `path` | relative path | a file node's path |
| `commits` | int ≥ 1 | counted commits that added or modified the path |
| `authors` | int ≥ 1 | distinct normalized author e-mails of those commits (bus factor) |

## GraphDocument (changed)

Gains `history: History = NOT_COLLECTED`. The schema version goes from 7 to 8. `extractors` gains
`"history-reader": "1.0.0"`, which is always present, whatever the status.

## GitHistorySource (`history/`, in memory only)

Where the reader gets objects: a dulwich object store, the snapshot commit SHA, the shallow set, and whether the
snapshot is dirty.

| Source | How it is made |
|---|---|
| Local folder | `Repo(root)` |
| GitHub | the bare repository filled by the fetch (research R5) |
| ZIP | no git source, reason `zip` |
| Folder without `.git` | no git source, reason `no_git` |

Never serialized. Author e-mails exist only inside the reader.

## Hotspot item (`graph/results.py`, `Item`)

`Item` gains three optional fields, used only by `hotspots`:

| Field | Type |
|---|---|
| `commits` | int ≥ 1 |
| `authors` | int ≥ 1 |
| `score` | int ≥ 1, = `commits × transitive_dependents` |

The answer also uses the existing `transitive_dependents` and `direct_dependents` fields. `node` is `file:<path>`
and `kind` is `file`.

## Hotspots answer (`Answer`, changed)

- `question` gains `hotspots`.
- `Answer` gains `history`: the `History` without `files`, serialized as `history`.
- Items are sorted by `(-score, -commits, -transitive_dependents, path)`.
- `options` is `{include_type_only, limit}`.
- `total` counts hotspots before the limit.

## Claim (verifier, changed)

`Claim` gains `metric` (`commits` \| `authors` \| `score` \| `transitive_dependents` \| `direct_dependents`) and
`value` (int ≥ 0). Both are optional, given together, and allowed only for `question: "hotspots"` with a `member`.
`Reason` gains `history_unavailable`.

## State: history of one analysis

```text
collect ─┬─ no .git / content snapshot ───────────→ not_available(no_git)      final
         ├─ ZIP source ───────────────────────────→ not_available(zip)         final
         ├─ --no-history ─────────────────────────→ not_available(skipped)     retryable
         ├─ .git unreadable / alternates ─────────→ not_available(unreadable)  final
         ├─ GitHub fetch: network/HTTP error ─────→ not_available(fetch_failed) retryable
         ├─ GitHub fetch: pack > max_archive_bytes → not_available(too_large)  retryable
         ├─ time up before the first commit ──────→ not_available(time_limit)  retryable
         ├─ time up while reading ────────────────→ partial                    retryable
         └─ window read to the end ───────────────→ available                  final
```

A stored analysis with a retryable history is replaced the next time the same snapshot is analyzed with a final
history (research R6).
