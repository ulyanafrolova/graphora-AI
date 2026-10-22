---

description: "Task list for 001-python-graph-cli"
---

# Tasks: Python Import Graph CLI

**Input**: Design documents from `specs/001-python-graph-cli/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/graph.schema.json,
contracts/cli.md, quickstart.md

**Tests**: Required. FR-020, FR-021 and constitution Principle VIII require golden, determinism and schema
tests. Within each story, write the tests first and confirm they fail before you implement.

**Organization**: Tasks are grouped by user story:

- US1 (P1): the import graph with provenance;
- US2 (P2): the coverage report;
- US3 (P3): byte-identical output and git snapshot ids.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: The user story the task belongs to (US1, US2 or US3)

Paths are relative to the repository root. Python code lives in `backend/src/graphora/`, tests in
`backend/tests/` and fixtures in `fixtures/repos/`.

---

## Phase 1: Setup

**Purpose**: Project initialization, the contract file and the governance change.

- [ ] T001 Create `backend/pyproject.toml` for a uv project:
  - name `graphora`, version `0.1.0`, `requires-python = ">=3.12"`, src layout;
  - dependencies `tree-sitter==0.26.0`, `tree-sitter-python==0.25.0` and `dulwich==1.2.19`;
  - dev dependency group with `pytest==9.1.1` and `jsonschema==4.26.0`;
  - console script `graphora = "graphora.cli:main"`;
  - `[tool.pytest.ini_options] testpaths = ["tests"]`.

  Do not run `uv sync` yet: the package does not exist until T002.
- [ ] T002 Create the package skeleton with an empty `__init__.py` in each folder, using exactly the
  folders listed in plan.md § Source Code:
  - `backend/src/graphora/`, `cli/`, `ingest/`, `detect/`, `adapters/`, `adapters/python/`, `resolve/`
    and `graph/`;
  - test folders `backend/tests/{golden,contract,integration,unit}/`.

  Then run `uv sync` in `backend/` and commit `backend/uv.lock`.
- [ ] T003 [P] Copy `specs/001-python-graph-cli/contracts/graph.schema.json` to `schema/graph.schema.json`
  without changes.
- [ ] T004 [P] Create `.gitattributes` at the repository root containing the line
  `fixtures/repos/** -text`.
- [ ] T005 [P] Amend `.specify/memory/constitution.md` (FR-016a):
  - in Principle III, change the snapshot id definition to "commit SHA, `<sha>+dirty:<content-hash>` for
    uncommitted trees, or `content:<content-hash>` for folders that are not a git working-tree root";
  - set the version to `1.0.1` and Last Amended to `2026-10-22`.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: The graph model, canonical serialization, the folder walk, the content snapshot and test
helpers. Every story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T006 [P] Write `backend/tests/unit/test_serialize.py`. It must assert:
  - nodes are sorted by `id`;
  - edges are sorted by `(source, line, column, target, symbol or "")`;
  - definitions are sorted by `(line, name)`;
  - coverage files and skipped entries are sorted by `path`;
  - edge `id` is `"e:" + sha256("source|line|column|target|symbol")[:16]`, with an empty string for a
    `null` symbol;
  - output ends with exactly one `\n`, has keys sorted at every level, is UTF-8 with no `\r`, and does not
    escape non-ASCII characters;
  - serializing the same model twice gives identical bytes.
- [ ] T007 [P] Write `backend/tests/contract/test_schema.py`. It validates against
  `schema/graph.schema.json` with `jsonschema.Draft202012Validator`.
  - Valid case: a minimal valid document built by the serializer.
  - Rejected cases (one test each):
    - an edge without `snippet_hash`;
    - an edge with `confidence: "unresolved"` and no `reason`;
    - an edge with `confidence: "resolved"` whose target starts with `unresolved:`;
    - a node `path` of `../x.py`;
    - `schema_version: 2`;
    - snapshot `abc`.
- [ ] T008 [P] Write `backend/tests/unit/test_walk.py`, using pytest `tmp_path`. It must assert:
  - files are listed as sorted POSIX relative paths;
  - each folder name in FR-009 (`.git`, `.venv`, `venv`, `env`, `node_modules`, `__pycache__`,
    `site-packages`, `dist`, `build`, `.tox`, `.mypy_cache`, `.pytest_cache`) is reported once as skipped
    with reason `excluded_dir`, and its contents are not listed;
  - a folder below the root that contains `.git` is skipped with reason `nested_repository`;
  - file and folder symlinks are skipped with reason `symlink` and are never followed;
  - `*.min.js` and `*.min.css` files are skipped with reason `minified`;
  - `LimitExceeded` is raised, naming the limit, when there are more than `max_files` non-skipped files or
    more than `max_bytes` total bytes;
  - skipped items do not count toward the limits;
  - `LimitExceeded("seconds", ...)` is raised when a `Deadline` that has already expired is passed in.
- [ ] T009 [P] Write `backend/tests/unit/test_hashes.py`. It must assert:
  - the content hash follows research.md § R4: SHA-256 over sorted paths, where each file contributes
    `path` bytes, `\0`, the file's sha256 hex digest and `\n`; the result is truncated to 16 hex;
  - the content hash is the same for a copy at a different absolute path;
  - the content hash changes when one byte changes;
  - the snippet hash is the same for `from  a  import (b,\n c)` and `from a import (b, c)`, differs for
    `from a import b`, and has the format `sha256:<16 hex>`.
- [ ] T010 Implement `backend/src/graphora/graph/model.py` with frozen dataclasses matching data-model.md:
  - `Definition(kind, name, line)`;
  - `FileNode(path, definitions)`, with id `file:<path>`;
  - `ExternalNode(name, category)`, with id `ext:<name>`;
  - `UnresolvedNode(reference)`, with id `unresolved:<reference>`;
  - `Edge(source, target, symbol, line, column, snapshot, confidence, reason, extractor, snippet_hash)`,
    where `reason` is required if and only if `confidence == "unresolved"` (check this in
    `__post_init__`);
  - `CoverageFile(path, language, status, flags)`;
  - `Skipped(path, reason)`;
  - `GraphDocument(snapshot, extractors, nodes, edges, files, skipped)`.

  Use `Literal` types for the enums: confidence `resolved|heuristic|unresolved`; reason
  `not_found|relative_beyond_top|namespace_package|dynamic`; status `analyzed|detected_only|not_code`;
  flags `parse_error|unreadable`; skip reason `excluded_dir|nested_repository|symlink|minified`.
- [ ] T011 Implement `backend/src/graphora/graph/serialize.py`. It provides:
  - `edge_id(edge)`;
  - `to_dict(doc)`, which applies all the sort orders from T006, computes `coverage.summary` (counts plus
    `by_language` with sorted keys) and sets `schema_version: 1`;
  - `dumps(doc) -> bytes`, which calls `json.dumps(sort_keys=True, ensure_ascii=False, indent=2)`, adds
    `"\n"` and encodes as UTF-8.

  Make T006 and T007 pass.
- [ ] T012 Implement `backend/src/graphora/ingest/walk.py`:
  - `walk(root: Path, max_files: int, max_bytes: int) -> WalkResult(files: list[str], skipped:
    list[Skipped], total_bytes: int)`;
  - use `os.scandir` with `follow_symlinks=False` and sort entries by name at each level;
  - apply the skip rules from data-model.md § Skipped;
  - raise `LimitExceeded(limit, value, observed)`;
  - never open files outside `root`;
  - define `Deadline(seconds)` using `time.monotonic()`, with a `check()` method that raises
    `LimitExceeded("seconds", ...)`, and call it once per directory entry. The deadline is used only for
    the limit, never in the output.

  Make T008 pass.
- [ ] T013 Implement `backend/src/graphora/ingest/snapshot.py` with `content_hash(root, files) -> str`
  (16 hex, research § R4) and `snapshot_id(root, files) -> str`. For now `snapshot_id` returns
  `content:<hash>`; US3 adds the git forms. Also add `snippet_hash(text) -> str` in
  `backend/src/graphora/graph/serialize.py`. Make T009 pass.
- [ ] T014 Create `backend/tests/conftest.py` with:
  - `REPO_ROOT` (resolved from the file location);
  - `FIXTURES = REPO_ROOT / "fixtures/repos"`;
  - a `run_analyze(dir, *args) -> (exit_code, stdout_bytes, stderr_text)` helper that calls
    `graphora.cli.main(argv)` in-process and captures streams;
  - a `project(doc: dict, sections: set[str]) -> dict` helper that turns a graph document into the
    hand-checkable shape from research § R10:
    - `nodes`: sorted list of `{id, kind}`, plus `category` for external nodes and `definitions` for file
      nodes;
    - `edges`: sorted list of `{source, target, symbol, line, confidence, reason}`;
    - `coverage`: sorted list of `{path, language, status, flags}`;
    - `skipped`: sorted list of `{path, reason}`;
    - `snapshot_kind`: one of `sha`, `dirty` or `content`.

**Checkpoint**: the serializer, walk and hashes are tested, and user stories can start.

---

## Phase 3: User Story 1 — trustworthy import graph (Priority: P1) 🎯 MVP

**Goal**: `graphora analyze <dir>` writes a schema-valid graph containing:

- file nodes with their definitions;
- external nodes (`stdlib` or `third_party`);
- `unresolved:` placeholder nodes;
- one `imports` edge per imported name, with full provenance.

**Independent Test**: `uv run pytest tests/golden -k "nodes or edges"` passes for `py-flat`,
`py-src-layout` and `py-dynamic`. The projected `nodes` and `edges` equal `expected.json` exactly.

### Fixtures and tests for US1 (write first, confirm they fail)

- [ ] T015 [P] [US1] Create the fixture `fixtures/repos/py-flat/repo/` with these files:
  - `main.py`: `import os`, `import requests`, `from pkg import a`, `from pkg.a import helper`,
    `import pkg.sub.deep`.
  - `pkg/__init__.py`: `from .a import helper`.
  - `pkg/a.py`: `from .b import f` on **line 3**; `def helper()`; `class Service` with method `run`.
  - `pkg/b.py`: `from . import a` (this closes the cycle a↔b); `def f()`.
  - `pkg/c.py`:
    - `from .missing import x`, which gives `unresolved:pkg.missing` with reason `not_found`;
    - `from ...toohigh import y`, which gives `unresolved:...toohigh` with reason `relative_beyond_top`;
    - `from .a import *`, which gives symbol `*`;
    - `import json`;
    - `import pkg.nope`, which gives `unresolved:pkg.nope` with reason `not_found`;
    - `from pkg import sub`, which resolves to `pkg/sub/__init__.py`;
    - `from requests import Session, adapters`, which gives two edges to `ext:requests`.
  - `pkg/sub/__init__.py` (empty).
  - `pkg/sub/deep.py`: `async def go()`.
  - `top.py`: `from . import main`, which gives reason `relative_beyond_top`.
- [ ] T016 [P] [US1] Create the fixture `fixtures/repos/py-src-layout/repo/` with these files:
  - `pyproject.toml` (static text only).
  - `src/app/__init__.py`.
  - `src/app/core.py`: `class Engine` with method `start`.
  - `src/app/core.pyi`: a stub (the `.py` wins in the module index).
  - `src/app/api/__init__.py`.
  - `src/app/api/routes.py`: `from app.core import Engine` and `from ..core import Engine`, both resolving
    to `src/app/core.py`.
  - `src/nsp/plugin.py`, with no `__init__.py` in `src/nsp`, so `nsp` is a namespace package.
  - `tests/test_core.py`:
    - `import app.core`, resolving to `src/app/core.py`;
    - `from app import core`, resolving to `src/app/core.py` with symbol `core`;
    - `import pytest`, giving `ext:pytest` (`third_party`);
    - `from nsp import plugin`, resolving to `src/nsp/plugin.py`;
    - `import nsp`, giving reason `namespace_package`.
- [ ] T017 [P] [US1] Create the fixture `fixtures/repos/py-dynamic/repo/` with these files:
  - `loader.py`:
    - `import importlib`;
    - `importlib.import_module(name)`, which gives `dynamic`;
    - `importlib.import_module("plugins.alpha")`, resolving to `plugins/alpha.py`;
    - `__import__("json")`, giving `ext:json`;
    - `import importlib as il` followed by `il.import_module(".rel")`, which gives `dynamic`;
    - `from importlib import import_module` followed by `import_module(f"plugins.{x}")`, which gives
      `dynamic`.
  - `plugins/__init__.py`.
  - `plugins/alpha.py`.
  - `plugins/evil.py`: on import, writes `Path(__file__).with_name("IMPORTED_MARKER")`. Add a comment
    saying it exists for the safety test.
  - `typing_stuff.py`:
    - an import under `if TYPE_CHECKING:`;
    - an import inside a function;
    - `try: import ujson` / `except ImportError: import json`.

  The US2-specific files are added in T030.
- [ ] T018 [US1] Write `fixtures/repos/py-flat/expected.json` and `fixtures/repos/py-src-layout/expected.json`
  by hand, with `nodes` and `edges` sections in the T014 projection shape. Check every line number against
  the fixture source. Do not generate these files with the tool.
- [ ] T019 [US1] Write `fixtures/repos/py-dynamic/expected.json` by hand, with `nodes` and `edges`
  sections. `IMPORTED_MARKER` must not be listed anywhere.
- [ ] T020 [P] [US1] Write `backend/tests/unit/test_extract.py` for the Python adapter, using inline source
  strings. Cover:
  - each import form: `import a`, `import a.b as c`, `from a import b, c`, `from . import x`,
    `from ..y import *`, and parenthesized multi-line imports;
  - correct 1-based line and column numbers;
  - imports inside functions, `if` and `try` blocks are found;
  - each dynamic form from T017 is classified as literal or non-literal, with its exact call text;
  - definitions: module-level `class`, `def` and `async def`, methods of module-level classes, decorated
    defs (the line is the `def` line, not the decorator line), and nested defs are not listed;
  - a syntax error elsewhere in the file still yields the import above it, with `has_error = True`.
- [ ] T021 [P] [US1] Write `backend/tests/unit/test_resolve.py`. Give it a set of paths and an import
  record, and assert the target node and reason for every row of the data-model.md § Resolution table,
  plus these rules:
  - a local name wins over an external one with the same name;
  - `.py` wins over `.pyi`;
  - the `""` root wins over `src`;
  - stdlib classification comes from `stdlib_modules.txt` (`json` gives `stdlib`, `requests` gives
    `third_party`).
- [ ] T022 [US1] Write `backend/tests/golden/test_fixtures.py`. For each folder in `FIXTURES`:
  1. run `run_analyze(fixture/"repo")` and assert exit code 0;
  2. validate stdout against `schema/graph.schema.json`;
  3. assert `project(doc, sections)` equals `expected.json`, where `sections` are the top-level keys of
     that `expected.json`;
  4. assert every edge's `snapshot` equals the document's `snapshot`, and every edge has
     `extractor == "python-adapter@0.1.0"`.

### Implementation for US1

- [ ] T023 [P] [US1] Create `backend/scripts/gen_stdlib_list.py`. It prints the sorted union of
  `sys.stdlib_module_names` for each interpreter given on the command line, plus `__future__`, using
  `uv run --python 3.12/3.13/3.14 python -c ...`. Run it to produce
  `backend/src/graphora/resolve/data/stdlib_modules.txt`, one name per line, with a header comment
  `# python-stdlib@3.14.0`. Make sure the data file is included as package data in
  `backend/pyproject.toml`.
- [ ] T024 [US1] Implement `backend/src/graphora/adapters/python/extract.py`, and in
  `backend/src/graphora/adapters/python/__init__.py` set `NAME = "python-adapter"` and
  `VERSION = "0.1.0"`.
  - `extract(source: bytes) -> FileFacts(imports: list[ImportRecord], definitions: list[Definition],
    has_error: bool)`.
  - It parses with `tree_sitter.Parser(Language(tree_sitter_python.language()))`.
  - `ImportRecord(kind: "import"|"from"|"dynamic", module: str|None, level: int, names: list[str|None],
    literal: bool, text: str, line: int, column: int)`. `column` is the 1-based code-point column.
  - It walks the whole tree, so every scope is covered (research § R6).
  - It recognises `importlib` aliases and `from importlib import import_module`.
  - Definitions follow data-model.md § Definition.

  Make T020 pass.
- [ ] T025 [US1] Implement `backend/src/graphora/resolve/python.py`:
  - `build_index(paths) -> ModuleIndex`, covering roots `["", "src"]`, the `.py`-over-`.pyi` rule and the
    namespace set `NS`;
  - `resolve(file_path, record, index) -> list[Target]`, one target per name, where a target is a
    `file:`, `ext:` or `unresolved:` node plus `symbol` and `reason`;
  - an external `category` taken from `stdlib_modules.txt`;
  - `RESOLVER_VERSION = "0.1.0"`;
  - the rules exactly as in data-model.md § Resolution, with no other fallbacks.

  Make T021 pass.
- [ ] T026 [US1] Implement `backend/src/graphora/graph/build.py` with
  `build(root, max_files, max_bytes, deadline) -> GraphDocument`. Call `deadline.check()` before each file
  is parsed. The steps are:
  1. walk the folder;
  2. compute the snapshot id;
  3. for each `.py` or `.pyi` file, read its bytes and decode them with `tokenize.detect_encoding`
     (operating on the bytes, never executing anything);
  4. extract, then resolve;
  5. create nodes: a file node for every analyzed file, and external or unresolved nodes only when an
     edge targets them;
  6. create edges with `snippet_hash(record.text)` and `extractor = "python-adapter@0.1.0"`;
  7. set `extractors = {"python-adapter": "0.1.0", "python-resolver": "0.1.0", "python-stdlib":
     "3.14.0"}`.

  For now, coverage lists `.py` and `.pyi` files as `analyzed` and every other file as `not_code`
  (completed in US2).
- [ ] T027 [US1] Implement `backend/src/graphora/cli/__init__.py`, following contracts/cli.md:
  - `main(argv=None) -> int`, built on argparse with the `analyze <dir> [--out] [--max-files 5000]
    [--max-bytes 52428800] [--max-seconds 300]` subcommand;
  - exit code 2 when `<dir>` is missing or is not a folder, when `--out` resolves inside `<dir>`, or when
    the output cannot be written;
  - exit code 3 on `LimitExceeded`, with the message `file limit exceeded: N files > --max-files M` (and
    the byte equivalent);
  - an atomic write: a temp file in the `--out` parent folder, then `os.replace`, and nothing written on
    failure;
  - stdout output when `--out` is absent;
  - one stderr info line in the form `graphora: info: analyzed N files, E edges (U unresolved), snapshot
    <id>`.

  Make T022 pass for `nodes` and `edges`.
- [ ] T028 [US1] Write `backend/tests/integration/test_cli.py`. It must assert:
  - exit code 2 for a path that does not exist and for a path that is a file;
  - exit code 2 when `--out` is inside the analyzed folder, with that folder unchanged (compare file
    listings before and after);
  - exit code 3 with `--max-files 1`, with the `--out` file not created;
  - exit code 3 with `--max-seconds 0`, with the `--out` file not created;
  - exit code 0 on an empty folder, with a valid document that has no nodes;
  - writing to stdout when `--out` is omitted.

**Checkpoint**: US1 is complete. The graph for all three fixtures matches the hand-checked nodes and edges.

---

## Phase 4: User Story 2 — coverage report (Priority: P2)

**Goal**: every file is listed with its language and status (`analyzed`, `detected_only` or `not_code`)
and its flags (`parse_error`, `unreadable`). Skipped paths are listed with their reasons.

**Independent Test**: `uv run pytest tests/golden -k coverage` passes. The projected `coverage` and
`skipped` sections equal `expected.json` for all three fixtures.

### Fixtures and tests for US2

- [ ] T029 [P] [US2] Write `backend/tests/unit/test_languages.py`. For every extension in the
  data-model.md `detected_only` table, assert the expected language and status. Also assert:
  - `.py` and `.pyi` give `python` / `analyzed`;
  - `README.md` and `config.yaml` give `null` / `not_code`;
  - each marker file in the data-model.md list (`pyproject.toml`, `setup.py`, `setup.cfg`,
    `package.json`, `tsconfig.json`, `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle`) gives its language
    with status `not_code`, except `setup.py`, which is `.py` and therefore `analyzed`.
- [ ] T030 [US2] Extend `fixtures/repos/py-dynamic/repo/` with these files:
  - `broken.py`: `import os` on line 1 and a syntax error on line 3;
  - `latin1.py`: Latin-1 bytes (for example `\xe9`) with no coding cookie, so it is `unreadable`;
  - `web/app.ts`;
  - `README.md`;
  - `config.yaml`;
  - `static/app.min.js`;
  - `.venv/lib/site.py`;
  - `__pycache__/x.cpython-314.pyc`;
  - `link.py`, a git symlink to `plugins/alpha.py`.

  Commit the skipped folders with `git add -f`. Add the `broken.py` edge to the `edges` section of
  `fixtures/repos/py-dynamic/expected.json`.
- [ ] T031 [US2] Add hand-checked `coverage` and `skipped` sections to all three `expected.json` files in
  `fixtures/repos/*/expected.json`:
  - every non-skipped file appears exactly once (SC-004), including `pyproject.toml` (marker,
    `not_code`);
  - `broken.py` has flags `["parse_error"]`;
  - `latin1.py` has flags `["unreadable"]` and no edges;
  - `.venv` and `__pycache__` are listed once each as `excluded_dir`, `link.py` as `symlink`, and
    `static/app.min.js` as `minified`.

### Implementation for US2

- [ ] T032 [US2] Implement `backend/src/graphora/detect/languages.py` with
  `classify(path) -> (language | None, status)`, using the extension and marker tables from data-model.md
  § CoverageFile, copied exactly. Make T029 pass.
- [ ] T033 [US2] Update `backend/src/graphora/graph/build.py`:
  - use `detect.languages.classify` for every walked file;
  - set the `parse_error` flag when `FileFacts.has_error` is true, while keeping the extracted imports
    and definitions;
  - set the `unreadable` flag, with no edges and no definitions, when decoding fails;
  - still create a file node for both `parse_error` and `unreadable` files;
  - pass `WalkResult.skipped` into the document.

  Make T022 pass with the `coverage` and `skipped` sections.

**Checkpoint**: US1 and US2 both pass. A missing edge can now be told apart from a file that was not
analyzed.

---

## Phase 5: User Story 3 — same input, same bytes (Priority: P3)

**Goal**: output is byte-identical across runs and paths. Snapshot ids reflect git state without ever
running `git`.

**Independent Test**: `uv run pytest tests/golden -k determinism tests/integration/test_snapshot.py
tests/integration/test_safety.py` passes.

### Tests for US3

- [ ] T034 [P] [US3] Add `test_determinism` to `backend/tests/golden/test_fixtures.py`. For each fixture:
  - run 10 times and assert the outputs are byte-identical;
  - `shutil.copytree(..., symlinks=True)` the fixture into `tmp_path / "deep/other/path"`, analyze the
    copy, and assert the output is byte-identical to the original;
  - assert the output contains neither `str(REPO_ROOT)` nor `str(tmp_path)`.
- [ ] T035 [P] [US3] Write `backend/tests/integration/test_snapshot.py`. It builds temp repositories with
  `dulwich.porcelain` (`init`, `add`, `commit`), so the `git` binary is not needed, and asserts:
  - a clean tree gives the 40-hex HEAD SHA;
  - after one included file is modified, the id has the form `<sha>+dirty:<16 hex>`, and a second run
    gives the same id;
  - adding an untracked `.py` file makes the tree dirty;
  - a change only inside `.venv/` keeps the tree clean;
  - `.git` as a file (`gitdir: ...`) gives `content:<16 hex>`;
  - an unborn HEAD (`init` with no commit) gives `content:<16 hex>`;
  - a `.git` that is a symlink to a repository outside `root` gives `content:<16 hex>`;
  - a repository with `.git/objects/info/alternates` or `.git/commondir` gives `content:<16 hex>`.
- [ ] T036 [P] [US3] Write `backend/tests/integration/test_safety.py`. It must:
  - copy `fixtures/repos/py-dynamic/repo` to `tmp_path`, then initialise and commit it with dulwich;
  - write a `.gitattributes` file with `* filter=evil`, and add `[filter "evil"] clean = touch
    <tmp>/GIT_FILTER_MARKER` and `[core] fsmonitor = touch <tmp>/FSMONITOR_MARKER` to `.git/config`;
  - run the analysis;
  - assert that none of `IMPORTED_MARKER`, `GIT_FILTER_MARKER` and `FSMONITOR_MARKER` exist;
  - assert that the set of files under the copied folder is unchanged.

### Implementation for US3

- [ ] T037 [US3] Extend `backend/src/graphora/ingest/snapshot.py`, following research § R3:
  - use the git path only if `root/.git` is a real directory (checked with
    `os.lstat` / `stat.S_ISDIR`, not `Path.is_dir()`) and contains neither `objects/info/alternates` nor
    `commondir`. In that case open it with `dulwich.repo.Repo(root)`, without calling any porcelain status
    function;
  - read the HEAD commit's tree and recursively build `{path → blob id}`, dropping modes `0o120000` and
    `0o160000` and paths that the walk's skip rules exclude;
  - build the working map as `sha1(b"blob %d\0" % len + bytes)` over the included files;
  - return the SHA when the maps are equal, and `<sha>+dirty:<content_hash>` otherwise;
  - fall back to `content:<hash>` when `.git` is a file, when HEAD is unborn, or on any dulwich error.

  Make T035 and T036 pass.
- [ ] T038 [US3] Audit `backend/src/graphora/` for sources of non-determinism, and fix any you find:
  - unsorted `set` or `dict` iteration on output paths;
  - `os.listdir` without sorting;
  - `datetime` or `time` calls;
  - absolute paths in the output.

  Make T034 pass.

**Checkpoint**: all three stories pass, and the output is reproducible and safe.

---

## Phase 6: Polish & cross-cutting concerns

- [ ] T039 [P] Add `backend/tests/integration/test_performance.py`, marked `@pytest.mark.slow`. It
  generates 1,000 Python files in `tmp_path` (10 packages with 100 modules each, and 3 cross-imports per
  module) and asserts that the analysis finishes in under 30 seconds (SC-005). Register the `slow` marker
  in `backend/pyproject.toml`.
- [ ] T040 [P] Fill the `## Commands` section of `CLAUDE.md`:
  - `cd backend && uv sync`;
  - `uv run pytest`;
  - `uv run pytest -m "not slow"`;
  - `uv run graphora analyze <dir> --out graph.json`.
- [ ] T041 [P] Add a short "Quick start" section to `README.md` that shows `graphora analyze` and links to
  `schema/graph.schema.json`.
- [ ] T042 Run every step of `specs/001-python-graph-cli/quickstart.md` and fix any drift between it and
  the actual behaviour. For SC-006, pick 3 random edges from the `py-flat` output and confirm by hand that
  `source` at `line` contains the import of `symbol`.
- [ ] T043 Run the full suite twice in clean checkouts with `uv run pytest`, and confirm it is all green
  with identical outputs. Then open the PR for `001-python-graph-cli`.

---

## Dependencies & Execution Order

### Phase dependencies

- Setup (T001–T005) has no prerequisites. T002, which runs `uv sync`, follows T001. T003–T005 can run in
  parallel at any time.
- Foundational (T006–T014) depends on Setup and blocks all stories.
- US1 (T015–T028) depends on Foundational.
- US2 (T029–T033) depends on US1's `build.py` (T026). T029 and T032 can start right after Foundational.
- US3 (T034–T038) depends on US1 (T027 CLI). T035 and T037 depend only on Foundational T013 and can run
  in parallel with US1.
- Polish depends on all stories.

### Within each story

The order is: fixtures, then hand-written `expected.json`, then tests (confirm they fail), then
implementation (extract, then resolve, then build, then CLI), then the checkpoint.

### Story completion order

```
Setup → Foundational → US1 ─┬→ US2
                            └→ US3 → Polish
```

## Parallel examples

```text
# Foundational — the test files are independent:
T006 test_serialize.py | T007 test_schema.py | T008 test_walk.py | T009 test_hashes.py

# US1 — fixtures and unit tests together:
T015 py-flat | T016 py-src-layout | T017 py-dynamic | T020 test_extract.py | T021 test_resolve.py | T023 stdlib list

# US3 — the tests are independent of each other:
T034 determinism | T035 test_snapshot.py | T036 test_safety.py
```

Team split, following project-context.md § 13:

- Developer 2: T015–T025 (fixtures, adapter, resolver);
- Developer 1: T012–T013 and T035–T037 (walk, snapshot, safety);
- Developer 3: builds the UI against `schema/graph.schema.json` and the `expected.json` fixtures.

## Implementation strategy

1. **MVP (US1 only).** Complete Setup, Foundational and US1, then stop and validate. The goal is a correct
   import graph for the three fixtures, which the frontend can already consume. Snapshot ids are
   `content:` only.
2. **Add US2.** Coverage and skipped paths become complete.
3. **Add US3.** Git snapshot ids and the hardened determinism and safety tests.
4. **Polish**, then open the PR. Each checkpoint is a good commit point.
