# Research: Repository Ingest from GitHub and ZIP

Decisions behind [plan.md](plan.md). Each entry gives the decision, why, and what was rejected.

## R1. HTTP client

- **Decision**: Python standard library only: `urllib.request` with a custom opener. No new runtime
  dependency.
  - Every request sends `User-Agent: graphora/<version>`; GitHub rejects requests without one.
  - Redirects are followed only to `https://` URLs on `github.com`, `api.github.com` and
    `codeload.github.com`. Any other redirect is a remote failure.
  - The socket timeout of every request is the time left on the run's deadline (R7).
  - Tests replace the opener in `graphora.ingest.github` with a fake; no test touches the network (R10).
- **Rationale**: two plain GET requests do not justify `requests` or `httpx`. The standard library
  streams responses, which the extractor needs.
- **Alternatives considered**: `httpx` (good API, but a new dependency plus `httpcore`, `h11`, `anyio`);
  `requests` (same, plus no streaming size cap without extra code).

## R2. Resolving a ref to one commit SHA with one request

- **Decision**: `GET https://api.github.com/repos/<owner>/<repo>/commits/<ref>` with
  `Accept: application/vnd.github.sha`. The body is the bare commit SHA. With no ref, `<ref>` is `HEAD`,
  which GitHub resolves to the default branch.
  - The same endpoint accepts a branch, a tag, a full SHA and a short SHA; an ambiguous short SHA is
    refused by GitHub.
  - The body must match `^[0-9a-f]{40}$`. Anything else is a remote failure.
  - The ref is percent-encoded per path segment; `/` inside `--ref` is kept, since GitHub accepts it.
  - Before any request the ref is checked locally against git's ref-name rules (no space, control
    character, `~ ^ : ? * [ \`, `..`, `@{`, leading `-`, trailing `.lock` or `/`). A bad ref is bad input.
- **Status mapping** (spec clarification 2):

  | Response | Group | Message names |
  |---|---|---|
  | `404` | bad input | `github.com/<owner>/<repo>` (not found or private) |
  | `422` | bad input | the ref (not found or ambiguous) |
  | `409` | bad input | the repository (empty) |
  | `403` or `429` with `x-ratelimit-remaining: 0`, or with `retry-after` | remote | rate limit, and the retry time from `x-ratelimit-reset` (UTC) or `retry-after`, if present |
  | other `4xx`/`5xx`, connection error, timeout before the deadline | remote | the URL host and status or error |

- **Rationale**: one anonymous API request per run, as the spec assumes. The `sha` media type avoids
  parsing JSON.
- **Alternatives considered**: `GET /repos/<o>/<r>` then `/commits/<branch>` (two requests, halves the
  anonymous budget); `git ls-remote` (a `git` subprocess, forbidden since 001 R3); `/repos/.../tarball/<ref>`
  without resolving first (the branch can move between the call and the download, so the analyzed content
  would not be pinned to a known SHA).

## R3. Downloading the archive

- **Decision**: `GET https://codeload.github.com/<owner>/<repo>/tar.gz/<sha>`, using the resolved SHA, never
  the branch name (FR-003).
  - The response is streamed straight into the tar reader (R5); no archive file is stored on disk.
  - The compressed size is counted while reading. A `Content-Length` above `--max-archive-bytes` stops the
    run before reading; otherwise the run stops as soon as the count passes the limit.
  - GitHub writes a pax global header whose `comment` is the commit SHA. If it is present and differs from
    the resolved SHA, the run fails as a remote failure. This catches a wrong archive cheaply.
- **Rationale**: `codeload` is where the API tarball endpoint redirects to, and it does not count against
  the API rate limit, so a run costs exactly one API request.
- **Alternatives considered**: `api.github.com/repos/.../tarball/<sha>` (a second rate-limited request);
  the ZIP endpoint (needs random access, so it would have to be saved to disk first).

## R4. Detecting the kind of source

- **Decision** (spec clarification 1, FR-001): one positional argument.
  1. Starts with `https://` → GitHub link, parsed by the rules in [data-model.md § Source](data-model.md).
  2. An existing folder → local folder, exactly as before.
  3. An existing file whose first bytes are a ZIP signature (`PK\x03\x04`, or `PK\x05\x06` for an empty
     archive) → ZIP archive. If it then cannot be read as ZIP, that is an **invalid archive**.
  4. Anything else (missing path, a file without a ZIP signature) → bad input:
     `not a directory or ZIP archive: <arg>`.
- **Rationale**: the existing tests `test_missing_dir` and `test_path_is_file` expect status `2` and the
  text "not a directory" (FR-015, SC-006). Splitting "not a ZIP at all" (wrong kind of input) from "a
  damaged ZIP" (invalid archive) keeps both tests green and gives a more accurate message.
- **Spec correction**: the edge case added during clarification said any non-ZIP file is an invalid
  archive. It now says: a file without a ZIP signature is bad input; a file with one that cannot be read
  is an invalid archive.
- **Alternatives considered**: judging by the `.zip` extension (rejected in clarification); treating every
  non-folder file as an invalid archive (breaks `test_path_is_file`).

## R5. Safe extraction

- **Decision**: one in-house extractor for both formats, in `graphora/ingest/archive.py`. It reads entries
  with `tarfile` (stream mode `r|gz`) or `zipfile`, and never calls `extract`/`extractall` or the
  `tarfile` filters. Each entry is classified, checked, then written by our own code.
  - **Paths.** Names are decoded strictly as UTF-8 (R6), split on `/`, and rejected if absolute, with a
    drive letter, with a `\`, a NUL, an empty, `.` or `..` segment. Before writing, the target's real path
    is checked to be under the extraction folder as a second line of defence.
  - **Kinds.** Regular file → written. Directory → created. Symlink → not created; recorded as skipped
    `symlink` (FR-008). Hardlink, character or block device, FIFO, GNU sparse or any unknown type → the
    whole archive is rejected as unsafe (clarification 4). Tar pax and GNU long-name headers are handled by
    `tarfile`; the pax global header is read only for the SHA check in R3.
  - **Writing.** Every parent folder is created with `os.mkdir(..., 0o755)`, one level at a time. Files
    are opened with `O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW` and mode `0o644`, so a file is never
    executable and an existing path is never overwritten (FR-010). Data is copied in 64 KiB chunks.
  - **Conflicts.** The archive is rejected if two entries map to the same path, if a file and a folder
    share a path, or if any entry lies under a path recorded as a symlink. Paths are compared after
    `unicodedata.normalize("NFC", p).casefold()`, on every system, not only on case-insensitive disks.
    This keeps the result identical on Linux and macOS (Principle II); the spec edge case is tightened to
    say so.
  - **Limits** (R8). The entry count and extracted bytes are checked **before** each write. A chunk that
    would cross the extracted-size limit is not written, so at most the limit is ever on disk (SC-005).
  - **Top-level folder.** After extraction, if the extraction folder holds exactly one folder and nothing
    else (counting recorded symlinks), that folder is the project root (FR-013). Recorded symlink paths
    are made relative to the chosen root.
- **Rationale**: `tarfile`'s `data` filter (3.12+) covers paths and links but not our skip-and-report
  rule for symlinks, size limits, or case conflicts. Writing ourselves keeps one code path for tar and
  ZIP and makes every rule testable.
- **Alternatives considered**: `tarfile.extractall(filter="data")` plus a post-check (writes first, checks
  after; a bomb fills the disk before the check); `shutil.unpack_archive` (no limits at all).

## R6. ZIP specifics

- **Decision**:
  - The entry count from the central directory is checked against `--max-entries` before anything is
    written. Declared sizes are not trusted; bytes are counted while writing (R5).
  - Names: if the UTF-8 flag (bit 11) is set, the name is used as is. If not, `zipfile` has decoded it as
    cp437; it is re-encoded to the original bytes and decoded strictly as UTF-8 (this is what macOS and
    most modern tools write). Failure rejects the archive with the entry named.
  - A symlink is an entry whose Unix mode (`external_attr >> 16`) is `S_IFLNK`. Other non-regular Unix
    modes are rejected as unsafe.
  - Encrypted entries, unsupported compression methods and CRC errors make the archive invalid.
  - The archive file itself must not be larger than `--max-archive-bytes`.
- **Rationale**: these are the ways a ZIP can lie about itself; each has one test.

## R7. One deadline for the whole run

- **Decision** (clarification 3): the CLI creates `Deadline(--max-seconds)` before anything else and passes
  it to fetching, extraction and `build()`. `Deadline` gains `remaining() -> float`.
  - Each HTTP request uses `max(0.1, deadline.remaining())` as its socket timeout. A socket timeout or a
    slow read is checked against the deadline first: if the time is up, the result is the existing
    `seconds` limit error (status `3`); otherwise it is a remote failure.
  - The extractor calls `deadline.check()` per entry and per chunk.
- **Rationale**: a single upper bound for the whole run, which pipeline 007 relies on; a stalled server
  cannot hang the CLI.
- **Alternatives considered**: separate download timeout (rejected in clarification).

## R8. New limits and their defaults

- **Decision**: three new options, each checked as described in R3, R5 and R6.

  | Option | Default | Counts |
  |---|---|---|
  | `--max-archive-bytes` | `209715200` (200 MiB) | compressed bytes downloaded, or the ZIP file size |
  | `--max-extract-bytes` | `209715200` (200 MiB) | bytes written to disk |
  | `--max-entries` | `20000` | files and folders created on disk, markers included |

  Entries the walk would skip by name are written as empty markers (R9), so they cost one entry and no
  bytes. The defaults are 4× the walk limits (`--max-files 5000`, `--max-bytes` 50 MB), so a project that
  passes the walk is not rejected earlier, as the spec assumes.
- **Rationale**: generous enough for real repositories with large skipped folders, tight enough that a
  bomb stops after 200 MiB.
- **Alternatives considered**: deriving them from `--max-files`/`--max-bytes` (hidden coupling; a user
  raising one limit would silently raise another).

## R9. Matching the local walk without writing skipped content

- **Decision**: entries that the walk skips by name are materialised as **empty markers** instead of being
  written in full:
  - an entry whose parent path contains an excluded folder name (`node_modules`, `.venv`, ...) is not
    written, but that excluded folder is created empty;
  - an entry named `.git` (file or folder, at any depth) is created empty; nothing under it is written;
  - a file whose name ends with a minified suffix is created empty.

  The walk then reports exactly the same skipped paths and reasons as for a local clone: `excluded_dir`,
  `nested_repository` (an empty `sub/.git` marker is enough), `minified`. Recorded symlinks are added to
  the document's skipped list only if the walk would have reached them: not under an excluded folder and
  not under a folder holding a `.git` marker. They are merged and sorted by path after `build()` returns.
- **Consequences**:
  - No `.git` data from an archive is ever written, so no archive content is ever read by dulwich. For a
    ZIP the snapshot id is therefore always `content:<hash>` (FR-005): `snapshot_id()` finds an empty
    `.git` with no `HEAD` and falls back to the content hash; a test covers it.
  - `build()` needs no extra parameter for skipped symlinks; the merge happens in `graphora/ingest`.
- **Rationale**: FR-012 and FR-016 need the fetched folder to walk exactly like a clone. Markers do this
  while keeping `node_modules`-sized content off the disk and out of the size limit.
- **Alternatives considered**: writing everything (wastes disk and limit on content the walk ignores);
  an `extra_skipped` parameter on `build()` (widens the change to another owner's module for no gain).

## R10. Tests without network

- **Decision**:
  - An autouse fixture in `tests/conftest.py` replaces `socket.socket.connect` and
    `socket.create_connection` with a function that fails the test, so the suite provably runs offline
    (SC-006).
  - GitHub tests patch the opener in `graphora.ingest.github` with a fake that serves canned status codes,
    headers and bodies, including slow and endless bodies.
  - Tarballs and ZIPs, hostile or not, are built in memory by the tests with `tarfile` and `zipfile`.
    Nothing is generated into `fixtures/`.
  - SC-002 / FR-016: for each fixture repository the test commits the fixture into a temporary git
    repository with dulwich, builds a tarball of the same files with GitHub's `<owner>-<repo>-<sha7>/`
    prefix and pax comment, serves it through the fake, and compares the bytes with `graphora analyze` of
    the clean local clone. `py-dynamic` contains a symlink and `.venv`/`__pycache__` folders, so the
    skip-list merge and markers are covered.
- **Rationale**: real archives from GitHub would make tests flaky and slow; the format details that
  matter (prefix folder, pax header, symlink entries) are reproduced by the tests.

## R11. Cleanup and interruption

- **Decision**: `fetch_snapshot()` is a context manager around `tempfile.TemporaryDirectory(prefix="graphora-")`.
  The CLI keeps it open across fetch, `build()` and serialisation, and writes `--out` after leaving it.
  - `SIGINT` and `SIGTERM` raise inside the run; the context manager removes the folder; the CLI prints
    `graphora: error: interrupted` and exits with `130`.
  - `SIGKILL` and power loss cannot be handled; the folder then sits in the system temp folder with the
    `graphora-` prefix, where the OS cleans it up. This is stated, not tested.
  - Tests point `TMPDIR` at `tmp_path` and assert that no `graphora-*` entry remains after every success,
    failure and injected `KeyboardInterrupt` (SC-004).
- **Rationale**: `TemporaryDirectory` handles nested read-only paths and errors during cleanup; one owner
  for the temp folder.

## R12. Limits of byte-identity with a clone

- **Decision**: FR-016 holds for every repository whose `.gitattributes` uses neither `export-ignore` nor
  `export-subst`. GitHub applies these attributes when it builds archives, so such a tarball can differ from
  a clone. Graphora analyzes what GitHub serves for the SHA and does not try to undo the attributes. The
  spec gains an edge case saying so.
- **Rationale**: undoing them would mean fetching individual blobs over the API (one rate-limited request
  per file). The SHA still pins the content exactly; only the set of files differs.
- **Alternatives considered**: refusing repositories that use these attributes (they are legitimate and
  rare in source trees).

## R13. Repository name

- **Decision**: `github.com/<owner>/<repo>` in lower case, as GitHub owner and repository names are
  case-insensitive; for a ZIP, the file name without its last extension; for a local folder, the folder
  name. The name is not part of the graph document in this slice (schema unchanged); it is returned by
  `fetch_snapshot()` for features 005 and 007 and shown in the CLI's info line.
- **Rationale**: one canonical spelling, so that storage keyed by `(repository, snapshot id)` in 007 does
  not split one repository into two.

## R14. Link and `--ref` together

- **Decision**: a `/tree/<ref>` link together with `--ref` is bad input, even if both name the same ref. A
  `/tree/` link must have exactly one segment after `tree`; more segments are rejected with a message
  suggesting `--ref`.
- **Rationale**: one place states the ref; no silent precedence rule to remember.

## Implementation notes

Decisions made while implementing, not covered above.

- **Empty `.git` for GitHub archives.** A clone has a `.git` folder, which the walk reports as skipped
  `excluded_dir`; a tarball has none. `fetch_snapshot()` creates an empty `.git` in the extracted root, so
  the coverage report matches a clone byte for byte (FR-016). `snapshot_id()` is not called for GitHub
  sources, so the empty folder is never read.
- **Wrapper folder is exempt from markers (R9).** Marker rules apply below a single top-level wrapper
  folder, not to it, so a ZIP of a project folder named `build/` or `dist/` is not emptied. For ZIP the
  wrapper is found from the central directory before extraction; for tar.gz it is the first entry when it
  is a folder, as GitHub writes `<owner>-<repo>-<sha7>/` first.
- **Test hooks.** `graphora.ingest.github._open` and `_timeout`, and `graphora.ingest.archive._write`, are
  module-level so tests can replace the network, shorten the socket timeout and count bytes written.
- **tree-sitter 0.26.0 memory corruption** ([issue #8](https://github.com/ulyanafrolova/graphora-AI/issues/8)).
  Found during the manual GitHub check (quickstart step 5): parsing several files in one process can
  crash (exit 139) or write impossible definition lines into the graph. It is independent of 002 and
  reproduces with the adapters alone; `tree-sitter==0.25.2` does not have it. The GitHub-equals-clone
  check on a real repository is to be repeated after #8 is fixed.
