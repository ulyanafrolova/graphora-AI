# Data Model: End-to-End Pipeline (010)

Jobs live in memory in the running service only (FR-012). Nothing new is stored in PostgreSQL; a `done` job
points to an analysis stored under the 005 model. The graph schema does not change.

## Job

| Field | Type | Rules |
|---|---|---|
| `id` | string | 32 lower-case hex characters from `secrets.token_hex(16)`; not derived from the source or other ids (FR-009) |
| `source` | JobSource | fixed at creation |
| `limits` | JobLimits | fixed at creation; each value ≤ the server's value |
| `stage` | Stage | see transitions below |
| `result` | JobResult or null | set exactly when `stage == "done"` |
| `error` | JobError or null | set exactly when `stage == "failed"` |

Not part of the job's status: creation time, timings, queue position, the work folder path (R6).

## JobSource

One of:

| `kind` | Fields | Notes |
|---|---|---|
| `github` | `repository` (`github.com/<owner>/<repo>`, lower case), `ref` (string or null) | as parsed by `parse_source` (002) |
| `zip` | `name` (the uploaded file name), `repository` (name without its last extension) | 005 FR-002 naming |

## JobLimits

`max_files`, `max_bytes`, `max_seconds`, `max_archive_bytes`, `max_extract_bytes`, `max_entries`. Defaults are
the server's values, which default to the CLI's (`5000`, `52428800`, `300`, `209715200`, `209715200`,
`20000`). A client may lower any of them for its job (FR-015). Always reported in full in the status.

## Stage

```text
queued ──► resolving ──► fetching ──► analyzing ──► storing ──► done
   │           │            │             │            │
   │           └──► done (reused, GitHub: nothing downloaded)
   └───────────┴────────────┴─────────────┴────────────┴──► failed
```

- `resolving` happens only for GitHub; a ZIP job goes `queued → fetching`.
- A stage never moves backwards; `done` and `failed` are final (FR-006).
- `storing → done` with action `reused` also happens for a ZIP whose snapshot is already stored with current
  versions (`Store.put` decides, as in the CLI).
- A queued job is `failed/interrupted` when the service stops; a running job becomes so at its next deadline
  check (R7).

## JobResult

| Field | Type | Source |
|---|---|---|
| `repository` | string | the stored analysis |
| `snapshot` | string | commit SHA or `content:<hash>` |
| `action` | `stored` \| `replaced` \| `reused` | `StoreResult.action`, or `reused` from `find_reusable` |
| `files` | int | `coverage.files` with status `analyzed` in the stored graph |
| `edges` | int | number of edges in the stored graph |
| `unresolved` | int | edges with confidence `unresolved` |
| `warnings` | list of strings | the stored warnings (config files that could not be read), sorted |

The counts are computed from the stored graph bytes, exactly as the CLI's summary line (005 contracts/cli.md).

## JobError

| Field | Type | Rules |
|---|---|---|
| `kind` | `remote` \| `limit` \| `archive` \| `store` \| `invalid` \| `interrupted` \| `internal` | mapping in [research R11](research.md) |
| `message` | string | the CLI's reason; no server paths, URLs with credentials or tracebacks |

## JobRunner (service state, not serialized)

| Part | Rules |
|---|---|
| `jobs` | id → Job, every job since the service started (FR-012) |
| `queue` | FIFO of queued job ids, length ≤ `queue_size` (default 20); full → `too_many_jobs` (FR-010) |
| `workers` | number of jobs running at once (default 1) |
| `active` | dedup key → id of a GitHub job that is not finished (R10) |
| `work_dir` | locked with `flock` for the service's lifetime; one sub-folder per running job (R8) |
| `database_url` | each running job opens and closes its own `Store` (R3) |

All changes to `jobs`, `queue` and `active` happen under one lock; a status is serialized from a consistent
copy taken under that lock.
