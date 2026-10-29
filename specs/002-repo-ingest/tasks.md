---

description: "Task list for 002-repo-ingest"
---

# Tasks: Repository Ingest from GitHub and ZIP

**Input**: Design documents from `specs/002-repo-ingest/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R14), data-model.md, contracts/cli.md,
contracts/ingest-api.md, quickstart.md

**Tests**: Required. FR-019 requires an offline suite with recorded or synthetic responses and archives
built by the tests; constitution Principle VIII requires golden coverage of the `build()` change. Within
each story, write the tests first and confirm they fail before you implement.

**Organization**: Tasks are grouped by user story:

- US4 (P1): local folder analysis unchanged; `build()` accepts a snapshot id;
- US3 (P1): hostile archives cannot harm the machine (the extractor, tar and ZIP);
- US1 (P1): analyze a public GitHub repository by link;
- US2 (P2): analyze a ZIP archive.

US3 comes before US1 because every GitHub tarball goes through the extractor (spec: "It ships together
with Story 1"). US4 comes first because it guards the only change to another owner's module.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: The user story the task belongs to (US1–US4)

Paths are relative to the repository root. Code lives in `backend/src/graphora/`, tests in
`backend/tests/`. Run commands from `backend/`. Do not edit any existing test or `expected.json`
(FR-015, SC-006).

---

## Phase 1: Setup

**Purpose**: Test infrastructure that every story uses. No new dependencies (research R1).

- [X] T001 Add an autouse fixture `_no_network` to `backend/tests/conftest.py` (research R10). It
  monkeypatches `socket.socket.connect`, `socket.socket.connect_ex` and `socket.create_connection` with a
  function that raises `AssertionError("network access in tests")`. Add a test
  `backend/tests/unit/test_no_network.py` that asserts `urllib.request.urlopen("https://example.com")`
  raises that error.
- [X] T002 [P] Create `backend/tests/archives.py`, helpers that build archives in memory for tests (never
  written into `fixtures/`):
  - `make_tar_gz(entries, pax_comment=None) -> bytes`, where each entry is `(name, kind, data_or_target,
    mode)` and `kind` is one of `file`, `dir`, `symlink`, `hardlink`, `chr`, `fifo`; `pax_comment` writes
    a pax global header with `comment=<value>` as GitHub does;
  - `make_zip(entries, utf8_flag=True) -> bytes`, with the same entry kinds where ZIP can express them
    (symlink via `external_attr = (stat.S_IFLNK | 0o777) << 16`; `fifo` via `S_IFIFO`), plus options for
    raw non-UTF-8 name bytes and a stored "encrypted" flag bit;
  - `tar_of_dir(path, prefix) -> bytes` and `zip_of_dir(path, prefix=None) -> bytes`, which add every file,
    folder and symlink under `path` in sorted order with `prefix/` in front, keeping symlinks as symlink
    entries;
  - `bomb_zip(size)` and `bomb_tar_gz(size)`: one entry of `size` zero bytes, highly compressed.
- [X] T003 [P] Create `backend/tests/fake_github.py`: a `FakeGitHub` object usable as the opener in
  `graphora.ingest.github` (implemented in T025). It maps a URL to a canned response
  `(status, headers, body)`, where `body` is `bytes`, an iterator of chunks, or `"stall"` (blocks until the
  socket timeout passed in, then raises `TimeoutError`). It records every requested URL and the request
  headers so tests can assert "one API request", "no `Authorization` header" and the `User-Agent`.

---

## Phase 2: Foundational

**Purpose**: Error types, the shared deadline, the fetch interface for local folders, and the CLI wiring.
After this phase `graphora analyze <dir>` goes through `fetch_snapshot()` and behaves exactly as before.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 [P] Create `backend/src/graphora/ingest/errors.py` with `class IngestError(Exception)` and the
  subclasses `BadInput`, `UnsafeArchive`, `InvalidArchive`, `RemoteError` (data-model.md § Errors). Each
  takes one `message: str` that the CLI prints as is.
- [ ] T005 [P] Add `Deadline.remaining() -> float` to `backend/src/graphora/ingest/walk.py`: seconds left,
  never below `0.0`. Do not change `check()` or anything else in the file. Unit test in
  `backend/tests/unit/test_deadline.py`.
- [ ] T006 Create `backend/src/graphora/ingest/fetch.py` (contracts/ingest-api.md, data-model.md):
  - `@dataclass(frozen=True) IngestLimits(max_archive_bytes=209715200, max_extract_bytes=209715200,
    max_entries=20000)`;
  - `@dataclass(frozen=True) FetchedSnapshot(root: Path, repository: str, snapshot: str | None,
    skipped: tuple[Skipped, ...])`;
  - `with_skipped(doc, extra)`: `dataclasses.replace(doc, skipped=tuple(sorted(doc.skipped + extra,
    key=lambda s: s.path)))`, returning `doc` itself when `extra == ()`;
  - `@contextmanager fetch_snapshot(source, limits, deadline)`: for `LocalSource` yield
    `FetchedSnapshot(root=path.resolve(), repository=path.resolve().name, snapshot=None, skipped=())`
    with no temp folder. Leave `GitHubSource` and `ZipSource` branches raising `NotImplementedError`
    until US1 and US2.
- [ ] T007 Create `backend/src/graphora/ingest/source.py` with the `LocalSource`, `GitHubSource(owner, repo,
  ref)` and `ZipSource` dataclasses (frozen) and `parse_source(argument: str, ref: str | None) -> Source`.
  In this task implement only: existing folder → `LocalSource`; `--ref` given with a folder →
  `BadInput("--ref is allowed only with a GitHub link")`; anything else not yet handled →
  `BadInput(f"not a directory or ZIP archive: {argument}")`. The `https://` and ZIP branches are added
  in T024 and T031.
- [ ] T008 Rewire `backend/src/graphora/cli/__init__.py` (contracts/cli.md), keeping every existing
  message, default and status:
  - the positional argument keeps `dest="dir"` with `metavar="source"`; help text "a local folder, a
    GitHub link or a ZIP file";
  - add `--ref`, `--max-archive-bytes` (int, default `209715200`), `--max-extract-bytes` (int, default
    `209715200`), `--max-entries` (int, default `20000`);
  - add `EXIT_ARCHIVE, EXIT_REMOTE, EXIT_INTERRUPTED = 4, 5, 130`;
  - create `Deadline(args.max_seconds)` first, then `parse_source`, then
    `with fetch_snapshot(...) as fetched:` run `build(fetched.root, ..., snapshot=fetched.snapshot)`,
    `with_skipped`, and `dumps` inside the block; write `--out` or stdout **after** the block;
  - keep the "`--out` must not be inside the analyzed folder" check for `LocalSource` only;
  - map `BadInput` → `2`, `LimitExceeded` → `3`, `UnsafeArchive`/`InvalidArchive` → `4`, `RemoteError` → `5`,
    `KeyboardInterrupt` → print `graphora: error: interrupted`, return `130`;
  - add `_LIMIT_MESSAGES` entries `"archive_bytes": "archive size limit exceeded: at least {observed} bytes
    > --max-archive-bytes {value}"`, `"extract_bytes": "extracted size limit exceeded: at least {observed}
    bytes > --max-extract-bytes {value}"`, `"entries": "entry limit exceeded: at least {observed} entries
    > --max-entries {value}"`;
  - in `main()` install a `SIGTERM` handler that raises `KeyboardInterrupt` and restore the previous
    handler in `finally` (research R11). Install it only when running in the main thread.

**Checkpoint**: `uv run pytest` passes with no edits to existing tests.

---

## Phase 3: User Story 4 - Local folder analysis keeps working unchanged (Priority: P1)

**Goal**: `graph/build.py` takes an optional snapshot id; local output stays byte-identical.

**Independent Test**: the full pre-existing suite passes unchanged, and a caller-supplied snapshot id
appears in the document and every edge with nothing else changed.

### Tests for User Story 4

- [ ] T009 [P] [US4] In `backend/tests/unit/test_build_snapshot.py`: for every fixture in
  `fixtures/repos/`, `build(root, 5000, 50*1024*1024, Deadline(300))` serialized with `dumps` equals the
  output of `build(..., snapshot=None)`; and `build(..., snapshot="a"*40)` gives a document whose
  `snapshot` and every edge's `snapshot` is `"a"*40`, and which equals the default output after replacing
  the snapshot strings (FR-014, US4 scenario 2).
- [ ] T010 [P] [US4] In `backend/tests/integration/test_ingest_cli.py` add local-path tests:
  `--ref main` with a folder → status `2` and `--ref is allowed only with a GitHub link`; a missing path →
  `2` and `not a directory or ZIP archive`; the stdout bytes for `fixtures/repos/py-flat/repo` are
  identical with and without explicitly passing the three new limit options at their defaults.

### Implementation for User Story 4

- [ ] T011 [US4] Add `snapshot: str | None = None` as the last parameter of `build()` in
  `backend/src/graphora/graph/build.py`: when it is not `None`, use it and do not call `snapshot_id()`;
  otherwise keep the current line unchanged. No other change in `graph/` (plan, FR-014). Note in the PR
  description that this change needs review and approval from Ulyana as module owner.

**Checkpoint**: US4 done; the local path is provably unchanged.

---

## Phase 4: User Story 3 - Hostile archives cannot harm the machine (Priority: P1)

**Goal**: one safe extractor for tar.gz streams and ZIP files (research R5, R6, R8, R9).

**Independent Test**: hostile archives built in the tests are each handled as data-model.md § Archive
entry classification says; nothing appears outside the temp folder; the temp folder is gone afterwards.

### Tests for User Story 3

Write all of these in `backend/tests/unit/test_archive.py`, each case for both tar.gz and ZIP where the
format can express it. Each test runs the extractor into `tmp_path / "x"` and also asserts that
`tmp_path` contains nothing except `x` (no file outside).

- [ ] T012 [P] [US3] Path rejection tests (FR-007, US3 scenario 1): entries `/etc/x`, `C:/x`, `c:x`,
  `a\\b`, `a/../../x`, `..`, `a//b`, `./a`, a name with NUL, and a non-UTF-8 name (ZIP without the UTF-8
  flag and bytes `b"\xff.py"`; tar with a raw `b"\xff"` name). Each raises `UnsafeArchive` whose message
  contains the entry name.
- [ ] T013 [P] [US3] Link and special-entry tests (FR-008, clarification 4): a symlink `link.py →
  ../../etc/passwd` is not created and is returned in the skipped list as `Skipped("link.py", "symlink")`;
  a hardlink entry raises `UnsafeArchive` naming it; character device and FIFO entries raise
  `UnsafeArchive`; an entry `link.py/inner.py` after (and, in another test, before) a symlink `link.py`
  raises `UnsafeArchive`.
- [ ] T014 [P] [US3] Collision tests (spec Edge Cases): duplicate `a.py` twice; `A.py` and `a.py`;
  `café.py` in NFC and in NFD; a file `a` and an entry `a/b.py` — each raises `UnsafeArchive` naming both
  entries, on every OS.
- [ ] T015 [P] [US3] Limit tests (FR-009, SC-005, US3 scenario 3): `bomb_zip(100 * limit)` and
  `bomb_tar_gz(100 * limit)` with `max_extract_bytes=1_000_000` raise `LimitExceeded("extract_bytes",
  ...)`, and the total size of files under `tmp_path` never exceeded `1_000_000` (measure with a
  monkeypatched write counter, not only after the fact); `max_entries=10` with 11 files raises
  `LimitExceeded("entries", ...)` — for ZIP before any file is created; a tar.gz stream longer than
  `max_archive_bytes` raises `LimitExceeded("archive_bytes", ...)`; an expired `Deadline(0)` raises
  `LimitExceeded("seconds", ...)`.
- [ ] T016 [P] [US3] Content-safety tests (FR-010, US3 scenario 5): files with modes `0o755` and `0o4755`
  in the archive are written with mode `0o644`; folders get `0o755`; a `setup.py` that writes a marker file
  when run, and a `package.json` with a `postinstall` script, produce no marker; no subprocess is started
  (monkeypatch `subprocess.Popen` and `os.system` to fail).
- [ ] T017 [P] [US3] Marker and root tests (research R9, FR-013): entries under `node_modules/`, `.venv/`
  and `a/.git/` are not written but `node_modules/`, `.venv/` and `a/.git` exist empty; a root `.git/HEAD`
  entry leaves an empty `.git/` folder; `x.min.js` exists with size `0`; an archive whose entries all sit
  under `proj/` yields root `.../proj`, and with an extra top-level `README` yields the extraction folder;
  a symlink under `node_modules/` or under `a/` (which has `a/.git`) is not in the skipped list. Invalid ZIP
  tests: an encrypted entry, an unsupported compression method and a CRC mismatch raise `InvalidArchive`;
  a truncated gzip stream raises `InvalidArchive`.

### Implementation for User Story 3

- [ ] T018 [US3] Create `backend/src/graphora/ingest/archive.py` with the shared writer (research R5, R9):
  - `class _Writer(dest: Path, limits: IngestLimits, deadline: Deadline)` that owns the counters, the
    collision table keyed by `unicodedata.normalize("NFC", path).casefold()`, the set of symlink paths
    and the list of recorded `Skipped(path, "symlink")`;
  - `_check_name(raw) -> str`: strict UTF-8, split on `/`; reject absolute, drive letter (`^[A-Za-z]:`),
    `\`, NUL, empty, `.` or `..` segments with `UnsafeArchive(f"unsafe archive entry {name}: ...")`;
    a single trailing `/` on folder names is allowed;
  - `add_dir(path)`, `add_file(path, chunks: Iterable[bytes])`, `add_symlink(path)`: apply the
    classification table in data-model.md in this order — collision and symlink-prefix checks, entry
    limit, markers (import `EXCLUDED_DIRS`, `MINIFIED_SUFFIXES` and `is_excluded_path` from
    `graphora.ingest.walk`; never copy the lists), then the write;
  - folders: `os.mkdir(p, 0o755)` one level at a time, then `os.chmod(p, 0o755)`; files:
    `os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)` then `os.fchmod(fd, 0o644)`;
    before opening, assert `os.path.realpath(p)` is under `os.path.realpath(dest)`;
  - per 64 KiB chunk: `deadline.check()`, then raise `LimitExceeded("extract_bytes", limit, total +
    len(chunk))` **before** writing a chunk that would cross the limit;
  - `finish() -> tuple[Path, tuple[Skipped, ...]]`: choose the root (FR-013: exactly one folder and
    nothing else, counting symlinks), make skipped paths relative to it, drop symlinks the walk would not
    reach (under an excluded folder, or under a folder that contains a `.git` marker), sort by path.
- [ ] T019 [US3] In `backend/src/graphora/ingest/archive.py` add the two readers (research R5, R6):
  - `extract_tar_gz(stream: BinaryIO, dest, limits, deadline, expected_sha: str | None) -> (root,
    skipped)`: `tarfile.open(fileobj=stream, mode="r|gz")`; regular → `add_file` via `extractfile`;
    dir → `add_dir`; symlink → `add_symlink`; hardlink, chr, blk, fifo, sparse, other → `UnsafeArchive`;
    a pax global header with a `comment` different from `expected_sha` → `RemoteError("GitHub archive does
    not match commit <sha>")`; `tarfile.ReadError`, `EOFError`, `zlib.error`, `gzip.BadGzipFile` →
    `InvalidArchive`;
  - `extract_zip(path: Path, dest, limits, deadline) -> (root, skipped)`: file size >
    `max_archive_bytes` → `LimitExceeded("archive_bytes", ...)`; `len(infolist()) > max_entries` →
    `LimitExceeded("entries", ...)` before any write; names decoded as in research R6 (flag bit 11, else
    re-encode cp437 and decode strict UTF-8); Unix mode `S_IFLNK` → symlink, `S_IFDIR` or name ending `/`
    → folder, `S_IFREG` or no Unix mode → file, other modes → `UnsafeArchive`; `flag_bits & 0x1`
    (encrypted), `NotImplementedError`, `zipfile.BadZipFile`, CRC errors → `InvalidArchive`. Never call
    `extract`/`extractall`.

**Checkpoint**: `uv run pytest tests/unit/test_archive.py` passes; SC-003 and SC-005 are met at unit level.

---

## Phase 5: User Story 1 - Analyze a public GitHub repository by its link (Priority: P1) 🎯 MVP

**Goal**: `graphora analyze https://github.com/<owner>/<repo>[...]` produces the graph of exactly one
resolved commit, with the SHA as snapshot id.

**Independent Test**: with `FakeGitHub` serving a tarball of a fixture, the output is byte-identical to
the analysis of a clean local clone of the same fixture at the same commit.

### Tests for User Story 1

- [ ] T020 [P] [US1] In `backend/tests/unit/test_source.py`, link parsing (data-model.md § GitHub link
  rules, R14): accepted `https://github.com/o/r`, `.../r.git`, `.../r/`, `https://GitHub.com/O/R` (stored
  as `o`, `r`), `.../tree/v1`; rejected with `BadInput` mentioning the accepted forms: `http://github.com/o/r`,
  `https://gitlab.com/o/r`, `.../blob/main/x.py`, `.../o/r/extra`, `.../o/r?x=1`, `.../o/r#x`, `.../tree/`,
  owner longer than 39 characters, repo `..`; `.../tree/feature/x` → `BadInput` suggesting `--ref`;
  `.../tree/v1` with `--ref v1` → `BadInput("--ref given twice ...")`; ref names `a..b`, `a b`, `-x`,
  `x.lock`, `a~1`, `a@{1}` → `BadInput("invalid ref name: ...")`; `--ref feature/x` accepted.
- [ ] T021 [P] [US1] In `backend/tests/unit/test_github.py` with `FakeGitHub` (research R2, R3, R7):
  - resolve with no ref requests `/repos/o/r/commits/HEAD` with `Accept: application/vnd.github.sha` and a
    `graphora/` user agent, and no `Authorization` header;
  - `--ref feature/x` requests `/commits/feature/x`;
  - a body that is not 40 lower-case hex characters → `RemoteError`;
  - `404` → `BadInput` naming `github.com/o/r`; `422` → `BadInput` naming the ref; `409` → `BadInput`
    "repository is empty";
  - `403` with `x-ratelimit-remaining: 0` and `x-ratelimit-reset: 1793000000` → `RemoteError` whose
    message contains "rate limit" and the UTC time; `429` with `retry-after: 60` → "rate limit";
  - `500` and a connection error → `RemoteError`;
  - a redirect to `https://evil.example/` → `RemoteError`;
  - the tarball is requested from `https://codeload.github.com/o/r/tar.gz/<sha>`;
  - `Content-Length` above the limit → `LimitExceeded("archive_bytes", ...)` without reading the body;
  - a `"stall"` body with `Deadline(0.5)` → `LimitExceeded("seconds", ...)`; the same stall with a
    deadline of 300 s and a short fake socket timeout → `RemoteError`;
  - exactly one request goes to `api.github.com` per run.
- [ ] T022 [P] [US1] In `backend/tests/golden/test_ingest_equivalence.py`, for every fixture in
  `fixtures/repos/` (research R10, FR-016, SC-002): copy `repo/` to `tmp_path/clone` with
  `symlinks=True`, `porcelain.init`, add every file and symlink, commit with fixed author, committer and
  timestamps; `sha` = the new HEAD; serve `tar_of_dir(clone, f"o-r-{sha[:7]}")` with
  `pax_comment=sha` at the codeload URL and `sha` at the API URL; assert the stdout bytes of
  `run_analyze("https://github.com/o/r")` equal those of `run_analyze(clone)`, and that running the link
  twice gives identical bytes (US1 scenario 3). Exclude `.git` when building the tarball.
- [ ] T023 [P] [US1] In `backend/tests/integration/test_ingest_cli.py` add GitHub CLI tests with
  `FakeGitHub`: success prints `graphora: info: fetched github.com/o/r at <sha>`; statuses `2` (404, 422,
  409, bad link), `3` (archive size, stall past `--max-seconds`), `4` (tarball with `../x`), `5` (rate limit,
  500); in every failure case an existing `--out` file keeps its old bytes and stdout is empty (FR-018).

### Implementation for User Story 1

- [ ] T024 [US1] Extend `parse_source` in `backend/src/graphora/ingest/source.py` for arguments starting
  with `https://`, exactly per data-model.md § GitHub link rules: host `github.com` (case-insensitive),
  no query or fragment, `<owner>` 1–39 characters of letters, digits and `-`; `<repo>` 1–100 characters
  of letters, digits, `.`, `-`, `_`, not `.` or `..`, an optional `.git` suffix removed; optional trailing
  `/`; optional `/tree/<one segment>`; owner and repo lower-cased; the ref checked against git's
  ref-name rules (research R2); the error messages in contracts/cli.md § New messages.
- [ ] T025 [US1] Create `backend/src/graphora/ingest/github.py` (research R1–R3, R7):
  - module-level `_open(request, timeout)` built with `urllib.request.build_opener` and a redirect
    handler that allows only `https://` URLs on `github.com`, `api.github.com`, `codeload.github.com`;
    tests replace `_open`;
  - `resolve_sha(source, deadline) -> str` with headers `Accept: application/vnd.github.sha` and
    `User-Agent: graphora/<package version>`, ref percent-encoded per segment (`quote(ref, safe="/")`),
    `HEAD` when no ref; status mapping table in research R2;
  - `open_tarball(source, sha, limits, deadline) -> BinaryIO`: a reader over the response that counts
    bytes against `max_archive_bytes`, checks `Content-Length` first, and converts socket timeouts into
    `LimitExceeded("seconds", ...)` when the deadline has passed, else `RemoteError`;
  - every request uses `timeout=max(0.1, deadline.remaining())`; never send credentials.
- [ ] T026 [US1] Implement the `GitHubSource` branch of `fetch_snapshot` in
  `backend/src/graphora/ingest/fetch.py`: `resolve_sha` → `tempfile.TemporaryDirectory(prefix="graphora-")`
  → `extract_tar_gz(open_tarball(...), tmp, limits, deadline, expected_sha=sha)` → yield
  `FetchedSnapshot(root, f"github.com/{owner}/{repo}", sha, skipped)`; the temp folder is removed when the
  block exits for any reason.
- [ ] T027 [US1] In `backend/src/graphora/cli/__init__.py` print `graphora: info: fetched <repository> at
  <sha>` for a GitHub source before the summary line.

**Checkpoint**: US1 tests pass; `graphora analyze <link>` works end to end against the fake.

---

## Phase 6: User Story 2 - Analyze a project uploaded as a ZIP archive (Priority: P2)

**Goal**: `graphora analyze project.zip` produces the folder graph of its contents with `content:<hash>`.

**Independent Test**: a ZIP of a fixture, built in the test, gives the same graph as the fixture folder
apart from the snapshot id.

### Tests for User Story 2

- [ ] T028 [P] [US2] In `backend/tests/unit/test_source.py` add ZIP detection (research R4): an existing
  file starting with `PK\x03\x04` → `ZipSource` whatever its extension (`x.bin`); an empty ZIP
  (`PK\x05\x06`) → `ZipSource`; `README.md` → `BadInput("not a directory or ZIP archive: ...")`; `--ref`
  with a ZIP → `BadInput`.
- [ ] T029 [P] [US2] In `backend/tests/golden/test_ingest_equivalence.py` add, for every fixture:
  `zip_of_dir(repo, prefix="proj")` and `zip_of_dir(repo)` (no prefix) written to `tmp_path/proj.zip`;
  `run_analyze` output equals the folder output after replacing the document and edge snapshot strings;
  the ZIP snapshot matches `^content:[0-9a-f]{16}$`; two runs give identical bytes (US2 scenarios 1–3).
  Add one case where the ZIP contains `.git/HEAD` and `.git/config`: the snapshot is still `content:...`
  (research R9).
- [ ] T030 [P] [US2] In `backend/tests/integration/test_ingest_cli.py` add: `PK\x03\x04garbage` →
  status `4` "invalid ZIP archive"; a ZIP larger than `--max-archive-bytes` → `3`; success prints
  `graphora: info: extracted proj.zip`.

### Implementation for User Story 2

- [ ] T031 [US2] Extend `parse_source` in `backend/src/graphora/ingest/source.py`: an existing regular
  file whose first 4 bytes are `PK\x03\x04` or `PK\x05\x06` → `ZipSource(path)`; read only those 4 bytes.
- [ ] T032 [US2] Implement the `ZipSource` branch of `fetch_snapshot` in
  `backend/src/graphora/ingest/fetch.py`: temp folder as in T026, `extract_zip`, yield
  `FetchedSnapshot(root, path.name.rsplit(".", 1)[0] if "." in path.name else path.name, None, skipped)`
  (research R13; `snapshot=None` so `build()` computes `content:<hash>`, FR-005).
- [ ] T033 [US2] In `backend/src/graphora/cli/__init__.py` print `graphora: info: extracted <file name>`
  for a ZIP source.

**Checkpoint**: all four stories work independently.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T034 Create `backend/tests/integration/test_ingest_cleanup.py` (SC-004, FR-011, US3 scenario 4):
  set `TMPDIR` to `tmp_path / "tmp"` (and reset `tempfile.tempdir`) and, for a successful GitHub run, a
  successful ZIP run, and each failure (404, rate limit, stall, archive limit, extract limit, unsafe entry,
  invalid ZIP, and a `KeyboardInterrupt` raised from inside `build` via monkeypatch), assert that no
  `graphora-*` entry remains and that the interrupt case returns `130` with `graphora: error: interrupted`.
- [ ] T035 [P] Create `backend/tests/integration/test_safety_ingest.py` (existing safety tests stay
  untouched): a GitHub tarball and a ZIP containing
  `setup.py`, `conftest.py`, `package.json` with scripts and a `.git/hooks/post-checkout`, each writing a
  marker when run; after `run_analyze`, no marker exists anywhere under `tmp_path` and
  `subprocess.Popen` was never called (Principle I).
- [ ] T036 [P] Update `CLAUDE.md` § Commands with
  `uv run graphora analyze https://github.com/<owner>/<repo> [--ref <ref>] --out graph.json` and
  `uv run graphora analyze <file.zip> --out graph.json`.
- [ ] T037 Run `uv run pytest` with no network (the T001 guard enforces it) and confirm that no file under
  `backend/tests/` that existed before this branch was modified: `git diff --stat main -- backend/tests`
  must list only new files (FR-015, SC-006).
- [ ] T038 Run the steps in `specs/002-repo-ingest/quickstart.md` 1–4; run step 5 once by hand against a
  small public repository and record the result in the PR description.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: after Setup. Blocks every story.
- **US4 (Phase 3)**: after Foundational. Small; do it first because it touches `graph/build.py`.
- **US3 (Phase 4)**: after Foundational. Independent of US4.
- **US1 (Phase 5)**: needs US3 (extractor) and US4 (`build(snapshot=)`).
- **US2 (Phase 6)**: needs US3 (extractor). Independent of US1 and US4 (it passes `snapshot=None`).
- **Polish (Phase 7)**: after US1 and US2.

### Within Each Story

- Tests first; confirm they fail.
- `source.py` before `fetch.py` before the CLI line.
- In US3, T018 (writer) before T019 (readers).

### Parallel Opportunities

- T002 and T003; T004 and T005.
- After Foundational: US4 and US3 in parallel.
- Within US3: T012–T017 (one file, but independent test functions; split between people by test).
- Within US1: T020–T023 in parallel (different files, except T023 shares `test_ingest_cli.py` with T010
  — append, do not reorder).
- After US3: US1 and US2 in parallel, except that T024 and T031 both edit `source.py` and T026 and T032
  both edit `fetch.py`.

---

## Parallel Example: User Story 1

```bash
Task: "Link parsing tests in backend/tests/unit/test_source.py (T020)"
Task: "GitHub client tests in backend/tests/unit/test_github.py (T021)"
Task: "Clone equivalence golden test in backend/tests/golden/test_ingest_equivalence.py (T022)"
Task: "GitHub CLI status tests in backend/tests/integration/test_ingest_cli.py (T023)"
```

## Parallel Example: User Story 3

```bash
Task: "Path rejection tests (T012)"
Task: "Link and special-entry tests (T013)"
Task: "Limit tests (T015)"
```

---

## Implementation Strategy

### MVP First

1. Phases 1–2: test infrastructure, errors, fetch interface, CLI wiring; the suite stays green.
2. Phase 3 (US4): `build(snapshot=)` with golden proof; ask Ulyana for review early.
3. Phase 4 (US3): the extractor with every hostile case.
4. Phase 5 (US1): GitHub by link. **Stop and validate**: quickstart steps 1, 2, 4 and the manual step 5.
   This is the MVP: analysis by link with commit-pinned provenance.

### Incremental Delivery

5. Phase 6 (US2): ZIP upload, reusing the extractor.
6. Phase 7: cleanup and safety integration tests, docs, full offline run.

The whole feature is one PR (constitution: one feature = one branch = one PR).

---

## Notes

- [P] tasks touch different files or independent test functions and have no unfinished dependencies.
- Never edit an existing test or `expected.json`; never generate files into `fixtures/`.
- Never call `extractall`, never create a link, never run a subprocess, never send credentials.
- Commit after each task or logical group.
