# CLI Contract: `graphora serve` (changes in 010)

Base contract: [005 contracts/cli.md](../../005-storage-http-api/contracts/cli.md). `graphora analyze`
(with and without `--store`), `query` and `mcp` are unchanged byte for byte (FR-022); `analyze --store` now
calls the shared pipeline function ([pipeline-api.md](pipeline-api.md)) internally.

## `graphora serve`

```
graphora serve [--database <url>] [--host 127.0.0.1] [--port 8000]
               [--workers 1] [--queue 20] [--work-dir <dir>]
               [--max-files 5000] [--max-bytes 52428800] [--max-seconds 300]
               [--max-archive-bytes 209715200] [--max-extract-bytes 209715200] [--max-entries 20000]
```

| Option | Default | Meaning |
|---|---|---|
| `--workers` | `1` | jobs running at the same time (FR-010) |
| `--queue` | `20` | jobs that may wait; beyond that `429 too_many_jobs` |
| `--work-dir` | `<system temp>/graphora-jobs` | folder for uploads and extracted snapshots; locked while the service runs and emptied at start (R8) |
| `--max-*` | the `analyze` defaults | server limits for every job; clients may only lower them (FR-015) |

Values below 1 are a usage error (exit `2`). `--host` keeps its `127.0.0.1` default (FR-024).

Startup errors:

| Exit | When | stderr |
|---|---|---|
| `2` | bad option value; work folder cannot be created | `graphora: error: …` |
| `2` | another service holds the work folder | `graphora: error: work folder in use by another graphora serve: use --work-dir` |
| `6` | store unavailable | unchanged from 005 |

On shutdown (Ctrl+C / SIGTERM) the service stops accepting jobs, fails queued ones as `interrupted`, waits
for running jobs to stop at their next deadline check, and removes their folders.
