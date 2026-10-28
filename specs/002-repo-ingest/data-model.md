# Data Model: Repository Ingest from GitHub and ZIP

The graph document and `schema/graph.schema.json` do **not** change (schema v2 stays). Everything below
lives in memory for one run, in `backend/src/graphora/ingest/`. Research references: [research.md](research.md).

## Source

What the user asked to analyze. Parsed from the single positional argument plus `--ref` (R4).

| Variant | Fields | Built when |
|---|---|---|
| `LocalSource` | `path: Path` | the argument is an existing folder |
| `GitHubSource` | `owner: str`, `repo: str`, `ref: str \| None` | the argument starts with `https://` and is a valid link |
| `ZipSource` | `path: Path` | the argument is an existing file starting with a ZIP signature |

### GitHub link rules (FR-002, R14)

Accepted, case-insensitive host, no query or fragment:

```
https://github.com/<owner>/<repo>
https://github.com/<owner>/<repo>.git
https://github.com/<owner>/<repo>/
https://github.com/<owner>/<repo>/tree/<ref>      (exactly one segment after tree)
```

- `<owner>`: 1–39 characters, letters, digits and `-`. `<repo>`: 1–100 characters, letters, digits, `.`,
  `-`, `_`; not `.` or `..`. Both are stored in lower case (R13).
- `--ref <ref>` is allowed only with a link and only if the link has no `/tree/` part.
- A ref (from either place) must pass git's ref-name rules (R2).
- Rejected with the list of accepted forms: other hosts, `http://`, `/blob/...`, extra path segments, a
  query or fragment, `/tree/` with zero or several segments (the message suggests `--ref`).

## IngestLimits

| Field | CLI option | Default | Checked |
|---|---|---|---|
| `max_archive_bytes` | `--max-archive-bytes` | 209715200 | `Content-Length`, bytes read from the download, ZIP file size |
| `max_extract_bytes` | `--max-extract-bytes` | 209715200 | before each chunk is written |
| `max_entries` | `--max-entries` | 20000 | before each file or folder is created; ZIP: central directory count first |

The existing `--max-files`, `--max-bytes` (walk) and `--max-seconds` (whole run, R7) keep their meaning.
Crossing any limit raises the existing `LimitExceeded(limit, value, observed)` with a new `limit` key:
`archive_bytes`, `extract_bytes` or `entries`.

## FetchedSnapshot

Yielded by `fetch_snapshot()` (contract: [contracts/ingest-api.md](contracts/ingest-api.md)). Valid only
inside the `with` block.

| Field | Type | GitHub | ZIP | Local folder |
|---|---|---|---|---|
| `root` | `Path` | top folder inside the temp folder | temp folder, or its only top folder (FR-013) | the folder itself |
| `repository` | `str` | `github.com/<owner>/<repo>` | file name without last extension | folder name |
| `snapshot` | `str \| None` | full commit SHA | `None` → `build()` computes `content:<hash>` | `None` → computed as today |
| `skipped` | `tuple[Skipped, ...]` | symlinks found in the archive (R9) | same | `()` |

## Archive entry classification

Applied to every entry in archive order (R5, R6, R9). "Reject" stops the run; nothing is kept on disk.

| Entry | Outcome | Error group |
|---|---|---|
| Name not valid UTF-8, or contains NUL or `\` | reject, name the entry | unsafe archive |
| Absolute path, drive letter, empty / `.` / `..` segment, resolves outside | reject, name the entry | unsafe archive |
| Hardlink, device, FIFO, sparse, unknown type | reject, name the entry | unsafe archive |
| Same normalised path as an earlier entry; file vs folder clash; under a symlink path | reject, name both | unsafe archive |
| Symlink | not created; recorded as `Skipped(path, "symlink")` | — |
| Under an excluded folder name | not written; the excluded folder is created empty | — |
| Named `.git`, any depth | created empty (file or folder); nothing under it is written | — |
| File with a minified suffix | created empty | — |
| Folder | created, mode `0o755` | — |
| Regular file | written, mode `0o644`, bytes counted | — |
| Tar pax global header | read for the SHA check only (R3) | — |
| ZIP: encrypted, unsupported method, CRC error, unreadable | reject | invalid archive |

A recorded symlink is reported only if the walk would reach it (R9).

## Errors and exit status

New exception classes in `graphora/ingest/errors.py`; the CLI maps them to statuses
([contracts/cli.md](contracts/cli.md)).

| Exception | Exit | Raised for |
|---|---|---|
| `BadInput` | `2` (existing usage status) | bad argument or link, `--ref` misuse, bad ref name, repository not found / private, unknown or ambiguous ref, empty repository |
| `LimitExceeded` (existing) | `3` | any limit, including the run deadline |
| `UnsafeArchive` | `4` | rejected entries in the table above |
| `InvalidArchive` | `4` | a ZIP or gzip/tar stream that cannot be read |
| `RemoteError` | `5` | rate limit, connection or TLS error, timeout before the deadline, unexpected status, bad SHA body, pax SHA mismatch, redirect off GitHub |
| interruption | `130` | `SIGINT`, `SIGTERM` |

`UnsafeArchive` and `InvalidArchive` share status `4` (FR-017 lists them as one group); their messages
differ.

## Lifecycle of one run

```
parse argument ─▶ Source ─▶ fetch_snapshot ─┬─ Local: yield folder (no temp)
                                             ├─ GitHub: resolve SHA ─▶ stream tar.gz ─▶ extract ─▶ yield
                                             └─ ZIP: check size ─▶ extract ─▶ yield
                    inside the with block:  build(root, ..., snapshot) ─▶ merge skipped ─▶ serialize to bytes
                    after the block:        temp folder removed ─▶ write --out atomically or stdout
```

On any exception the temp folder is removed before the CLI prints the error; `--out` is untouched (FR-018).

## Change to `graph/build.py` (FR-014)

```
build(root, max_files, max_bytes, deadline, snapshot: str | None = None)
```

If `snapshot` is given, `snapshot_id()` is not called and that value goes into the document and every
edge. Otherwise behaviour is unchanged, so local output is byte-identical (FR-015). This is the only change
to the module; it is reviewed by its owner.
