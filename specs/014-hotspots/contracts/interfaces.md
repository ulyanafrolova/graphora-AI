# Contract: hotspots in the query layer, CLI, MCP and HTTP

## Query layer

```python
queries.hotspots(ix: GraphIndex, *, include_type_only: bool = True, limit: int | None = 10) -> Answer
```

- A negative `limit` raises `ValueError`, as in other queries.
- It never raises for missing history. The items are empty and `history.status` says why.

Answer JSON (`results.dumps`):

```json
{
  "snapshot": "3f1c…",
  "question": "hotspots",
  "target": null,
  "options": {"include_type_only": true, "limit": 10},
  "total": 14,
  "truncated": true,
  "items": [
    {
      "node": "file:auth/service.py", "kind": "file", "confidence": "resolved", "type_only": false, "chain": [],
      "commits": 47, "authors": 1, "score": 564, "transitive_dependents": 12, "direct_dependents": 5
    }
  ],
  "history": {
    "status": "available", "reason": null, "commit": "3f1c…", "window_start": "2025-11-26T10:00:00Z",
    "newest": "2026-11-26T10:00:00Z", "oldest": "2025-12-03T08:12:45Z",
    "commits_read": 312, "merges_skipped": 41, "shallow_skipped": 0, "local_changes": false
  },
  "completeness": {"unresolved_imports": 3, "not_analyzed_files": 0, "files_with_errors": 0}
}
```

Text rendering (`render_text`):

```text
hotspots @ 3f1c…
auth/service.py  score 564  commits 47  authors 1  transitive 12  direct 5
users/models.py  score 90  commits 9  authors 3  transitive 10  direct 2
history: 312 commits from 2025-12-03 to 2026-11-26 (window from 2025-11-26), 41 merges not counted
total: 14
truncated (limit 10)
completeness: 3 unresolved imports, 0 files not analyzed, 0 files with errors
```

What the `history:` line says in other cases:

| Case | `history:` line |
|---|---|
| `partial` | `history: partial (time limit), 6000 commits read back to 2026-03-01` |
| `not_available` | `history: not available (zip)`. The `skipped` reason reads `not available (skipped by request)` |
| `local_changes` | adds `; uncommitted changes not counted` |
| `shallow_skipped > 0` | adds `; N commits not counted (shallow history)` |

## CLI

`graphora analyze <source> [--no-history] …`
- History is on by default.
- `--no-history` writes `history` with `not_available` / `skipped`.
- Works with or without `--store`.
- A new info line goes to stderr after the summary: `history: <same text as the query footer line>`.
- No new exit codes: history problems never fail `analyze`.

`graphora query <graph.json> hotspots [--limit N] [--no-type-only] [--format text|json]`
- Takes no target.
- `--limit` defaults to 10, as for `key-files`.
- `--symbol`, `--max-depth`, `--follow-barrels` and `--level` are usage errors (exit 2), as for `key-files`.

## MCP

The tool `hotspots(include_type_only: bool = True, limit: int = 10)` is read-only, like the other tools. Its
limit is capped by `MAX_LIMIT`. Description (fixed text):

> Files that change often and that many files depend on: risk = commits in the 12 months before the snapshot
> commit × transitive dependents. Each item has commits, authors (bus factor: how many people changed it), score
> and dependents. The history note says how much history was read; when history is not available the list is
> empty and the note gives the reason. include_type_only=false leaves out TypeScript `import type` links.
> limit (default 10) caps the items.

`graph_overview` gains `history: {status, reason}` in JSON and a text line
`history: available | partial | not available (<reason>)`.

## HTTP API

`GET /api/v1/hotspots?repository=<name>&snapshot=<id>[&limit=N][&include_type_only=true|false]`

`limit` defaults to 10 and `include_type_only` to `true`, as in the CLI and MCP.

| Case | Response |
|---|---|
| Found | `200` with the answer JSON above, bytes equal to `results.dumps` |
| Unknown repository or snapshot | `404`, same messages as `/graph` |
| Bad `limit` (not an integer, negative), bad `include_type_only` (not `true`/`false`), unknown or repeated parameter | `400` |
| History not available | `200` with an empty `items` and `history.reason` |

The handler reads the stored graph only, through the query layer. No analysis, no writes.

Jobs:
- `POST /api/v1/jobs` body keys gain `history` (boolean, default `true`). A non-boolean value is a `400`.
- `POST /api/v1/jobs/zip?name=…[&history=true|false]` is accepted for symmetry; a ZIP has no history anyway.
- The job status body echoes `"history": true|false` next to `limits`.
- A GitHub job's deduplication key includes the flag.
