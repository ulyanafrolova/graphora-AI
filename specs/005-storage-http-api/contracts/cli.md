# CLI Contract: `graphora analyze --store` and `graphora serve` (changes in 005)

Base contract: [002 contracts/cli.md](../../002-repo-ingest/contracts/cli.md). This file lists only what 005
changes. Without `--store`, `graphora analyze` is unchanged byte for byte: output, messages, exit statuses,
and no database connection is attempted.

## `graphora analyze`

```
graphora analyze <source> [existing options] [--store] [--database <url>]
```

| Argument | Default | Meaning |
|---|---|---|
| `--store` | off | Save the analysis in the store, or reuse a stored one ([research R6](../research.md)) |
| `--database <url>` | `$GRAPHORA_DATABASE_URL` | PostgreSQL connection string. Only allowed with `--store` |

Behaviour with `--store`:

- **Output.** The graph is written to stdout or `--out` exactly as without `--store`. On reuse it is the stored
  bytes, which are identical for the same snapshot and extractor versions.
- **GitHub link.** The ref is resolved first. If a reusable analysis of `github.com/<owner>/<repo>` at that SHA
  exists, no archive is downloaded and nothing is written to the store.
- **Local folder, ZIP.** Analyzed as today; then stored, or left as is when a reusable analysis of the same
  pair exists.
- **Info line**, after the existing ones and before the summary:
  `graphora: info: stored <repository> <snapshot>`, `graphora: info: replaced <repository> <snapshot>` or
  `graphora: info: reused <repository> <snapshot>`.
- **Order.** The store write happens inside the fetch block (the temp folder still exists, but is not read
  again, R4); `--out` is written after the store transaction commits.

## `graphora serve`

```
graphora serve [--database <url>] [--host 127.0.0.1] [--port 8000]
```

Starts the read-only HTTP API ([http-api.md](http-api.md)). Opens the store first; if that fails, prints the
error and exits with status `6` without listening. Runs until `SIGINT`/`SIGTERM`, then exits `0`.

## Exit statuses

Existing statuses are unchanged. New:

| Status | Meaning | Message |
|---|---|---|
| `6` | Store unavailable: no URL given, cannot connect, or wrong store version | `graphora: error: store unavailable: <reason>` |
| `2` | `--database` without `--store` (usage) | `graphora: error: --database requires --store` |

The `<reason>` never includes the password from the connection string.
