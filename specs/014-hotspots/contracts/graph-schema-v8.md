# Contract: graph document schema v8

Changes from v7. Everything else is unchanged.

- `schema_version` is `8`.
- `extractors` always contains `"history-reader": "1.0.0"`.
- The top-level required keys gain `history`.

## `history`

All keys are always present. Keys are sorted, as in the rest of the document.

```json
{
  "history": {
    "status": "available",
    "reason": null,
    "commit": "3f1c…40 hex",
    "window_start": "2025-11-26T10:00:00Z",
    "newest": "2026-11-26T10:00:00Z",
    "oldest": "2025-12-03T08:12:45Z",
    "commits_read": 312,
    "merges_skipped": 41,
    "shallow_skipped": 0,
    "local_changes": false,
    "files": [
      {"path": "auth/service.py", "commits": 47, "authors": 1},
      {"path": "users/models.py", "commits": 9, "authors": 3}
    ]
  }
}
```

Not available (for example a ZIP, or a folder that is not a git root):

```json
{
  "history": {
    "status": "not_available",
    "reason": "zip",
    "commit": null,
    "window_start": null,
    "newest": null,
    "oldest": null,
    "commits_read": 0,
    "merges_skipped": 0,
    "shallow_skipped": 0,
    "local_changes": false,
    "files": []
  }
}
```

## Schema rules (`schema/graph.schema.json`)

| Key | Rule |
|---|---|
| `status` | enum `available`, `partial`, `not_available` |
| `reason` | null, or enum `no_git`, `zip`, `unreadable`, `skipped`, `fetch_failed`, `too_large`, `time_limit`, `not_collected` |
| `commit` | null or `^[0-9a-f]{40}$` |
| `window_start`, `newest`, `oldest` | null or `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$` |
| `commits_read`, `merges_skipped`, `shallow_skipped` | integer ≥ 0 |
| `local_changes` | boolean |
| `files[]` | objects with exactly `path` (relpath), `commits` (integer ≥ 1), `authors` (integer ≥ 1) |

The schema enforces with `if`/`then`:
- `not_available` ⇔ `reason` not null;
- for `not_available`: `commit` null and `files` empty.

`load.py` also checks:
- `files` sorted by path and unique;
- every path is a file node of the document;
- `authors ≤ commits`;
- a `commit` of an `available`/`partial` history equals the snapshot id's SHA part.

## Determinism

The section depends only on the snapshot commit's history and the extractor version. The one exception is
`partial` (research R7). No author names or e-mail addresses appear anywhere in the document (FR-015).

## Consumers to update in the same change

| Consumer | Update |
|---|---|
| `graph/serialize.py` | write the section |
| `graph/load.py` | read and check it |
| `schema/graph.schema.json` | v8 rules above |
| `store/store.py` | schema validation; reuse rule (research R6) |
| Tests | `tests/contract/test_schema.py`, `tests/unit/test_serialize.py`, `test_load.py`, `test_overview.py`, `tests/integration/test_store.py`, golden `test_fixtures.py` (new `history` section) |
| Fixtures | every `fixtures/repos/*/expected.json` gets `history` (`not_available`, `no_git`), by hand |

The frontend does not exist yet, so it has nothing to update.
