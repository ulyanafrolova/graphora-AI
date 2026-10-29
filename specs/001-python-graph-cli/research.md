# Research: Python Import Graph CLI

Every decision below resolves an open point from the plan's Technical Context. Versions were checked with
`uv pip install --dry-run` on 2026-10-22.

## R1. Python version and project tooling

- **Decision**:
  - Python `>=3.12`, managed with `uv`.
  - A single package `graphora` under `backend/src/graphora/` (src layout), configured in
    `backend/pyproject.toml`.
  - The CLI is exposed as the `graphora` console script.
- **Rationale**:
  - The constitution requires `uv`.
  - Python 3.12 is the oldest version still widely shipped, and it has every stdlib feature we need.
  - The dev machine runs 3.14, and all chosen dependencies install there.
- **Alternatives considered**:
  - Poetry and pip-tools: rejected because the constitution names `uv`.
  - Python 3.11: rejected because it gains nothing and soon leaves security support.

## R2. Parser

- **Decision**: `tree-sitter==0.25.2` (first 0.26.0, downgraded for memory corruption, issue #8) with `tree-sitter-python==0.25.0`, pinned exactly. The adapter version
  string `python-adapter@<version>` changes whenever the grammar pin or the extraction logic changes;
  `tests/unit/test_extractor_versions.py` fails when it does not.
- **Rationale**:
  - The constitution names Tree-sitter.
  - It tolerates errors: a file with a syntax error still yields a tree. `ERROR` and `MISSING` nodes mark
    the broken parts, and imports in the intact parts can still be extracted (spec US2-3).
  - It never imports or executes the code it parses (Principle I).
  - It reports exact row and column positions, which we need for provenance.
- **Alternatives considered**:
  - Stdlib `ast`: fails on the first syntax error, and its results depend on the Python version that runs
    the tool (new syntax breaks determinism across environments).
  - `libcst`: heavier, and it also fails on invalid syntax.

## R3. Snapshot id without running git

- **Decision**:
  - Do not run the `git` binary. Read `.git/` with `dulwich==1.2.19`, a pure-Python git implementation.
  - The folder counts as a git working-tree root only if `<dir>/.git` is a real directory, checked with
    `lstat` so a symlink does not count, and it has no `objects/info/alternates` or `commondir`. Each of
    these exclusions would make the snapshot depend on data outside the folder. A `.git` *file* (a
    worktree or a submodule) is also treated as not git. In all these cases the snapshot id is
    `content:<hash>`.
  - Clean versus dirty is decided by comparing git blob ids, not by `git status`:
    - The working map is `{relative path → sha1("blob <len>\0" + bytes)}` over the included files.
    - The HEAD map is `{path → blob id}` from the HEAD tree, filtered by the same skip rules. Symlinks
      (mode `120000`) and gitlinks (mode `160000`) are dropped.
    - Equal maps give `<sha>`. Otherwise the id is `<sha>+dirty:<content-hash>`.
- **Rationale**:
  - `git status` on an untrusted repository can run code configured by that repository: `core.fsmonitor`,
    or clean/process filters (`filter.*`) selected through `.gitattributes`. That breaks Principle I.
  - Comparing blob ids needs no index, no filters and no hooks.
  - The result is deterministic, and it matches the spec's definition: "the analyzed files equal the
    commit".
- **Alternatives considered**:
  - `git status --porcelain` with `-c core.fsmonitor=` and similar flags: rejected because the list of
    dangerous config keys is open-ended.
  - `dulwich.porcelain.status`: it depends on the index and the stat cache, so it is fragile, and it is
    blind to gitignored files that we still analyze.
  - Parsing `.git/HEAD` by hand: needs pack-file support, which dulwich already provides.

## R4. Content hash and snippet hash

- **Decision**:
  - **Content hash**: SHA-256 over the included files in sorted POSIX-path order. For each file, feed
    `path` UTF-8 bytes, then `\0`, then the SHA-256 hex digest of the file bytes, then `\n`. The id is
    written as `content:<first 16 hex chars>`, and the dirty form uses the same hash.
  - **Snippet hash**: `sha256:<first 16 hex>` of the import's source text, with every whitespace run
    collapsed to one space and the ends trimmed.
  - The imported text is the full statement (`import …` / `from … import …`), or for dynamic imports the
    call expression.
- **Rationale**:
  - The hashes depend only on paths and bytes, so copying the folder somewhere else gives the same output.
  - Normalizing whitespace keeps the hash stable under reformatting, while any change to the imported
    names changes it.
  - 64 bits is enough to tell snippets and snapshots apart at this scale, and it keeps the output readable.
- **Alternatives considered**:
  - Full 64-hex digests: needlessly long in a UI.
  - Hashing raw lines: breaks on indentation changes and does not cover multi-line imports.

## R5. Standard-library classification

- **Decision**:
  - Commit `backend/src/graphora/resolve/data/stdlib_modules.txt`. It is generated once from
    `sys.stdlib_module_names` of CPython 3.12, 3.13 and 3.14 (the union), plus `__future__`.
  - The file is versioned as `python-stdlib@3.14.0`. A small script in `backend/scripts/` regenerates it.
    That script runs only the local interpreter, never analyzed code.
- **Rationale**:
  - FR-011 requires that the classification does not depend on the running interpreter.
  - Using the union means that a module removed in 3.13 (such as `imp` or `distutils`) is still classed as
    stdlib for older projects.
- **Alternatives considered**:
  - Calling `sys.stdlib_module_names` at runtime: rejected because it is not deterministic across
    interpreters.
  - The `stdlib-list` package: an extra dependency that adds nothing.

## R6. Import resolution rules

- **Decision**: the rules, applied in this order, are specified in `data-model.md` § Resolution. In short:
  - **Module index.** Build `dotted name → file` for each source root, searching `""` first and then
    `src` (if it exists). `x/__init__.py` (or `.pyi`) is the package `x`. A `.py` file wins over a `.pyi`
    file for the same name. A folder with Python descendants and no `__init__` is a namespace package.
  - **`import a.b.c`.** The full dotted name must exist. If it does, the edge goes to that module file.
    If it does not but `a` is local, the edge is unresolved with reason `not_found`. If `a` is not local
    at all, the edge goes to the external node `a`.
  - **`from M import n`.** If `M.n` is a module, the edge goes to it, with symbol `n`. Otherwise it goes to
    the file of `M`, with symbol `n`. `*` is recorded as symbol `*`.
  - **Relative imports.** The base package is the importing file's module name under its root, minus the
    last part (an `__init__` file keeps its own name). Going above the top gives reason
    `relative_beyond_top`, and so does a relative import in a top-level module.
  - **Pure namespace target with no file to point to** gives reason `namespace_package`.
  - **Dynamic imports.** `importlib.import_module(x)`, bare `import_module(x)` (when the file imports it
    from `importlib`) and `__import__(x)`:
    - a plain string literal is resolved like `import x`;
    - a literal starting with `.`, or anything that is not a literal, is unresolved with reason `dynamic`.
- **Rationale**:
  - These rules follow Python's real import semantics.
  - Wherever the semantics depend on runtime state (`sys.path`, the working directory, the `package=`
    argument), the result is `unresolved` and nothing is guessed (Principle IV).
- **Alternatives considered**:
  - Following re-exports in `__init__.py`: deferred to the slice that adds symbol nodes.
  - Reading source roots from `pyproject.toml`: deferred, as the spec's Assumptions say.

## R7. Serialization

- **Decision**:
  - Build plain dicts and lists, sorting every list explicitly:
    - nodes by `id`;
    - edges by `(source, line, column, target, symbol or "")`;
    - coverage files and skipped entries by `path`;
    - definitions by `(line, qualified_name)`.
  - Write with `json.dumps(..., sort_keys=True, ensure_ascii=False, indent=2)` plus `"\n"`, encoded as UTF-8
    with LF line endings.
  - Write atomically: create a temp file in the target folder, then `os.replace`.
- **Rationale**: Principle II, and FR-002 ("no partial output file").
- **Alternatives considered**:
  - `orjson`: faster, but an extra dependency that is not needed at this size.
  - Canonical JSON (RFC 8785): unnecessary while there is only one producer.

## R8. CLI framework

- **Decision**: stdlib `argparse`. Exit codes:
  - `0`: success;
  - `2`: usage error or invalid input;
  - `3`: a limit was exceeded.

  Diagnostics go to stderr, and the graph goes to stdout only when there is no `--out`.
- **Rationale**: no dependency is needed for one subcommand.
- **Alternatives considered**: Typer and Click. Either can be adopted later, when more subcommands arrive.

## R9. Graph library

- **Decision**: NetworkX is not added in this slice.
- **Rationale**:
  - The spec has no graph queries. The cycle requirement is met by both edges being present.
  - The in-memory model plus the serializer live in `graphora/graph/`, ready for NetworkX in the queries
    slice.
- **Alternatives considered**: adding NetworkX now. That means a dependency without a use, against the
  CLAUDE.md rule "no scaffolding ahead of a spec".

## R10. Golden test design

- **Decision**:
  - Each fixture lives at `fixtures/repos/<name>/repo/`, and its ground truth at
    `fixtures/repos/<name>/expected.json`, outside the analyzed folder.
  - `expected.json` is a hand-written, readable *projection* of the output:
    - node ids, kinds and definitions;
    - edges as `(source, target, symbol, line, confidence, reason)`;
    - coverage statuses;
    - skipped paths;
    - the snapshot id kind.
  - The golden test projects the real output to the same shape and asserts exact equality. Nothing may be
    missing and nothing may be extra.
  - Hash values are checked in unit tests, not by hand.
  - `fixtures/repos/** -text` goes in `.gitattributes`, so checkouts never rewrite line endings.
  - Skipped folders (`.venv/`, `__pycache__/`) are committed with `git add -f`, and a symlink is committed
    as a git symlink.
- **Rationale**:
  - Hashes and exact snapshot strings cannot be checked by hand, but the structure can.
  - Separating the ground truth from the analyzed folder prevents `expected.json` from analyzing itself.
- **Alternatives considered**: comparing full byte-for-byte output files. That is still done for
  determinism (run twice, and run from a copied temp path), but it is not used as ground truth.
