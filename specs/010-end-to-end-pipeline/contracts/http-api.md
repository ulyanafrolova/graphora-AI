# HTTP API Contract: Jobs (changes in 010)

Base contract: [005 contracts/http-api.md](../../005-storage-http-api/contracts/http-api.md). Its common rules
(UTF-8 JSON, sorted keys, no extra whitespace, error shape, no server paths in messages) apply here. The
three 005 `GET` endpoints are unchanged (FR-022). This file adds three endpoints and changes one error
message.

## Changes to 005

- The API is no longer read-only: it can start analyses (FR-023, replaces 005 FR-018). It still offers no
  operation that changes or deletes stored data in any other way.
- `405 method_not_allowed`: the message becomes `method not allowed` (it said `only GET is allowed`).
- New error kinds:

| HTTP | `kind` | When |
|---|---|---|
| 413 | `limit` | upload larger than `max_archive_bytes`; message names the limit and its value |
| 429 | `too_many_jobs` | the queue already holds `queue_size` waiting jobs |
| 503 | `stopping` | a job is submitted while the service is shutting down: `the service is stopping` |

## Job status body

Returned by all three endpoints below.

```json
{"error":null,
 "id":"5f0c9e0d7a1b4c3e9f2a6b8d1c0e3f4a",
 "limits":{"max_archive_bytes":209715200,"max_bytes":52428800,"max_entries":20000,
           "max_extract_bytes":209715200,"max_files":5000,"max_seconds":300},
 "result":{"action":"stored","edges":42,"files":12,"repository":"github.com/o/r",
           "snapshot":"3f2a…40 hex…","unresolved":3,"warnings":[]},
 "source":{"kind":"github","ref":"main","repository":"github.com/o/r"},
 "stage":"done"}
```

(Shown wrapped; the real body has no whitespace.)

- `stage`: `queued`, `resolving`, `fetching`, `analyzing`, `storing`, `done`, `failed` ([data-model.md](../data-model.md)).
- `result` is non-null only for `done`; `error` only for `failed`:

```json
{"error":{"kind":"limit","message":"file limit exceeded: at least 5001 files > max_files 5000"},
 "id":"…","limits":{…},"result":null,
 "source":{"kind":"zip","name":"app.zip","repository":"app"},"stage":"failed"}
```

- `max_seconds` is a JSON number; the other limits are integers.
- No timestamps, timings or queue positions. The same job state gives byte-identical bodies (FR-009).
- After `done`, read the graph with `GET /api/v1/graph?repository=<result.repository>&snapshot=<result.snapshot>`,
  or start the MCP server with `graphora mcp --repository … --snapshot …` (FR-021).

## `POST /api/v1/jobs` — start from a GitHub link

Request body, `Content-Type: application/json`:

```json
{"github":"https://github.com/o/r","ref":"main","limits":{"max_files":1000}}
```

| Key | Required | Rules |
|---|---|---|
| `github` | yes | a GitHub repository link accepted by the CLI (002): `https://github.com/<owner>/<repo>[.git][/]` or `…/tree/<ref>` |
| `ref` | no | a git ref name; not allowed when the link has `/tree/<ref>` |
| `limits` | no | any subset of the six limit keys; each ≥ 1 and ≤ the server's value |

No other keys are allowed. Responses:

| HTTP | When |
|---|---|
| `202` | job created, or an identical unfinished job exists (same id returned, FR-011); body = job status |
| `400 bad_request` | not JSON, unknown key, invalid link or ref, ref given twice, bad limit; message gives the CLI's reason |
| `429 too_many_jobs` | queue full |

A value that is not a link (a local path, a ZIP path, any non-GitHub URL) is `400`
`not a GitHub repository link: …`; the server never looks at its file system for it (FR-003).

## `POST /api/v1/jobs/zip?name=<file name>[&max_files=<n>]…` — start from a ZIP upload

The request body is the archive bytes (`Content-Type: application/zip` or `application/octet-stream`).
Query parameters: `name` (required) and any of the six limit keys.

| HTTP | When |
|---|---|
| `202` | job created; body = job status with `source.kind = "zip"` |
| `400 bad_request` | missing or unsafe `name` (empty, `/`, `\`, NUL, `.`, `..`, longer than 255 bytes, repository name longer than 300 characters), unknown parameter, bad limit, empty body, body not starting with a ZIP signature (`not a ZIP archive: <name>`) |
| `413 limit` | `Content-Length` or the received bytes exceed `max_archive_bytes`: `archive size limit exceeded: at least <n> bytes > max_archive_bytes <limit>`; reading stops at once (FR-017) |
| `429 too_many_jobs` | queue full; checked before the body is read |

Uploads are never deduplicated before analysis; two identical uploads produce one stored analysis.

## `GET /api/v1/jobs/{id}`

| HTTP | When |
|---|---|
| `200` | body = job status |
| `404 not_found` | `job not found: <id>` — unknown id, an id from before a restart, or a malformed id |

No query parameters are allowed.
