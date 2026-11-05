# HTTP API Contract (005, read-only)

Served by `graphora serve` ([cli.md](cli.md)) on `127.0.0.1:8000` by default. All operations are `GET`; no
operation changes stored data or starts an analysis (FR-018). Import over HTTP is feature 007.

All query values must be percent-encoded. In particular `+` in a `<sha>+dirty:<hash>` snapshot is `%2B`; an
unencoded `+` decodes to a space and the snapshot is then not found.

## Common rules

- Bodies are UTF-8 JSON. Non-graph bodies use sorted keys and no extra whitespace (R11).
- The same stored data and the same request always give byte-identical bodies (FR-016).
- Unknown query parameters are a `bad_request`.
- Errors:

```json
{"error":{"kind":"not_found","message":"snapshot not found: github.com/o/r 3f…"}}
```

| HTTP | `kind` | When |
|---|---|---|
| 400 | `bad_request` | missing or malformed parameter, bad line range |
| 404 | `not_found` | repository, snapshot or path not stored; names which one |
| 503 | `store_unavailable` | the database cannot be reached |
| 500 | `internal` | unexpected error; fixed message, details only in the server log |

Messages never contain server file paths, connection strings or stack traces.

## `GET /api/v1/repositories`

```json
{"repositories":[
  {"name":"github.com/o/r","snapshots":["3f2a…40 hex…","9c1b…"]},
  {"name":"py-flat","snapshots":["content:0123456789abcdef"]}
]}
```

Repositories sorted by name; snapshots sorted as strings (FR-012). An empty store returns
`{"repositories":[]}`.

## `GET /api/v1/graph?repository=<name>&snapshot=<id>`

`200`, `Content-Type: application/json`, body = the stored graph document bytes, unchanged (FR-013), as
defined by `schema/graph.schema.json`. `404` names whether the repository or the snapshot is missing.

## `GET /api/v1/file?repository=<name>&snapshot=<id>&path=<path>[&start=<n>][&end=<n>]`

`path` must equal a `coverage.files[].path` of that snapshot exactly — no normalization of case, `./`, `\`,
or trailing `/` (FR-014, FR-015). Anything else is `404 path not found in snapshot: <path>`. The handler reads
only the store.

`start` and `end` are optional 1-based inclusive line numbers. Defaults: `start=1`, `end=line_count`.
`bad_request` when `start < 1`, `end < start`, or `start > line_count` (for a non-empty file); `end` past the
last line is clamped to `line_count`.

Text file:

```json
{"path":"src/a.py","has_text":true,"line_count":12,"start":3,"end":5,
 "lines":[{"n":3,"text":"from b import f"},{"n":4,"text":""},{"n":5,"text":"def g():"}]}
```

File without text (binary, not decodable, or unreadable during analysis; R5):

```json
{"path":"logo.png","has_text":false,"line_count":0,"start":0,"end":0,"lines":[]}
```

`start`/`end` on a file without text is a `bad_request`. An empty text file returns `line_count: 0`,
`start: 0`, `end: 0`, `lines: []`.

Line splitting and decoding follow [research R5](../research.md): line `n` here is line `n` of every edge
that cites this file.
