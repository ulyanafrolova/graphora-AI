# Feature Specification: Python Import Graph CLI

**Feature Branch**: `001-python-graph-cli`

**Created**: 2026-10-22

**Status**: Draft

**Input**: User description: "Python-only CLI: graphora analyze <dir> --out graph.json. Builds a deterministic import graph with provenance on every edge, defined by schema/graph.schema.json v1, with a coverage report. Golden tests over 2–3 fixture repos in fixtures/repos/ with hand-checked expected.json, covering relative imports, src layout, a cycle, an external package and an unresolved dynamic import. No DB, no API, no UI, no LLM."

## Clarifications

### Session 2026-10-22

- Q: Should the first slice also extract class and function definitions as nodes, or only files and
  external packages? → A: Files and external packages only. Each file node carries a list of its
  definitions (class/function/method, qualified name, line). There are no symbol nodes and no symbol edges.
- Q: What snapshot id should a folder get when it is not its own git working-tree root? → A:
  `content:<hash>` of the included files. This PR also makes a PATCH amendment to constitution
  Principle III to allow that form.
- Q: What should an edge point to when its import target cannot be determined? → A: A placeholder node
  `unresolved:<import as written>`. Identical texts share one node.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get a trustworthy import graph of a Python project (Priority: P1)

A developer points the command at a local Python project folder and receives one graph file. In it, every
project file is a node, every external package is a node, and every import statement is an edge. Each edge
says where it was written (file, line, snapshot) and how sure the tool is about its target: `resolved`,
`heuristic` or `unresolved`.

**Why this priority**: The graph is what every later Graphora feature uses: the UI, the graph queries, MCP
and the agents. If edges are wrong or have no provenance, nothing built on top can be trusted.

**Independent Test**: Run the command on each fixture repository and compare the output with its
hand-checked `expected.json`. All expected edges and nodes must be present, and nothing extra may appear.

**Acceptance Scenarios**:

1. **Given** a project where `pkg/a.py` has `from .b import f` on line 3, **When** the developer runs the
   analysis, **Then** the graph has an edge `pkg/a.py → pkg/b.py` with symbol `f`, line 3, confidence
   `resolved`, the snapshot id, the extractor name@version and a snippet hash.
2. **Given** a project using a `src/` layout (`src/app/...`) with tests that `import app`, **When** analyzed,
   **Then** the test files' imports resolve to files under `src/app/`.
3. **Given** `x.py` imports `y.py` and `y.py` imports `x.py`, **When** analyzed, **Then** both edges are
   present, and the cycle can be read from the graph without extra input.
4. **Given** a file with `import requests` and `import json`, where no local module has either name,
   **When** analyzed, **Then** each import is an edge to an external package node. `requests` is labeled
   third-party and `json` is labeled standard library.
5. **Given** a file calling `importlib.import_module(name)` with a variable argument, **When** analyzed,
   **Then** an edge with confidence `unresolved` is recorded at that line. No target file is guessed.

---

### User Story 2 - See exactly what was and was not analyzed (Priority: P2)

Along with the graph, the developer sees a coverage report that lists every file in the folder. Each file has
a status: fully analyzed, detected only (a known language that is not analyzed yet), or not code. The report
also lists the paths that were skipped and why.

**Why this priority**: Graphora claims full analysis only where it does analysis. Without coverage, a missing
edge could mean "no dependency" or it could mean "not looked at", and the user cannot tell which.

**Independent Test**: Run on a fixture that contains Python files, TypeScript files, a README, a config file
and a virtual-environment folder. Compare the coverage section with `expected.json`.

**Acceptance Scenarios**:

1. **Given** a project with `.py`, `.ts`, `README.md` and `config.yaml` files, **When** analyzed, **Then**
   the `.py` files are `analyzed`, the `.ts` files are `detected_only`, and the README and YAML are
   `not_code`.
2. **Given** a project containing `.venv/`, `node_modules/` and `__pycache__/`, **When** analyzed, **Then**
   their contents are not analyzed, and each skipped folder appears once in the report with its reason.
3. **Given** a Python file with a syntax error, **When** analyzed, **Then** the file is still listed as
   `analyzed` with a parse-error flag, and imports from its readable parts are still kept.

---

### User Story 3 - Same input, same bytes (Priority: P3)

The developer or a CI job runs the analysis twice on the same snapshot, on the same or a different machine,
and gets byte-identical output files.

**Why this priority**: Reproducibility is the product's main claim against chat agents. It also makes golden
tests and caching possible.

**Independent Test**: Analyze each fixture several times, from different working directories and different
absolute paths, and compare the output files byte by byte.

**Acceptance Scenarios**:

1. **Given** an unchanged project, **When** it is analyzed 10 times in a row, **Then** all 10 output files
   are byte-identical.
2. **Given** the same project copied to two different absolute paths, **When** both copies are analyzed,
   **Then** the outputs are byte-identical, and no absolute path or timestamp appears in them.
3. **Given** a project that is a git working tree with uncommitted changes, **When** analyzed, **Then** the
   snapshot id has the form `<sha>+dirty:<content-hash>`. Running again without further changes gives the
   same id.

---

### Edge Cases

- **Relative import above the top-level package** (`from ... import x` at depth 1): recorded as `unresolved`.
- **Relative or local-looking import whose target file does not exist** (`from . import missing`): recorded
  as `unresolved`. It is not turned into an external package.
- **`from pkg import name` where `name` is both a submodule and could be an attribute**: resolves to the
  submodule file if it exists. Otherwise it resolves to `pkg/__init__.py`, with `name` recorded as the
  symbol.
- **`import a.b.c`**: one edge to `a/b/c.py` or `a/b/c/__init__.py` when the full dotted name exists. If it
  does not exist but `a` is local, the edge is `unresolved` with reason `not_found`. There is no fallback to
  a parent module.
- **Folders without `__init__.py`** (namespace packages): treated as packages for resolution.
- **Same name exists locally and as an external package**: the local module wins.
- **Dynamic import with a literal string argument** (`importlib.import_module("pkg.mod")`,
  `__import__("pkg")`): resolved by the normal rules. With a non-literal argument: `unresolved`.
- **Imports inside functions, under `if TYPE_CHECKING:`, or in `try/except ImportError` blocks**: recorded
  like any other import.
- **The same target imported twice in one file**: two edges, one for each statement and line.
- **Symbolic links**: never followed. They are reported as skipped.
- **Files that cannot be decoded as text**: listed in coverage with reason `unreadable`, and no edges.
- **Files that cannot be read** (for example, no read permission): listed in coverage with the `unreadable`
  flag, no edges, and left out of the content hash. A folder that cannot be listed stops the run with a clear
  error and exit status 2, because its files could not be accounted for.
- **Special files** (FIFOs, sockets, device files): listed in coverage with the `unreadable` flag and never
  opened, since reading a FIFO can block forever.
- **Empty folder or a folder with no Python files**: a valid graph with only coverage entries. Exit status is
  success.
- **Path that does not exist or is not a folder**: a clear error message, a failure exit status, and no
  output file written.
- **Folder over the size, file-count or time limit**: refused with a clear message naming the limit that
  was exceeded.
- **Nested git repositories** (a folder below the root that contains `.git`): skipped with reason
  `nested_repository`.
- **Minified files** (`*.min.js`, `*.min.css`): skipped with reason `minified`.
- **A `.git` that is a symlink, or a git repository whose objects live outside the folder** (alternates,
  `commondir`): the snapshot falls back to `content:<hash>`, and nothing outside the folder is read.

## Requirements *(mandatory)*

### Functional Requirements

**Command**

- **FR-001**: Users MUST be able to run `graphora analyze <dir> [--out <file>]`. Without `--out`, the graph
  is written to standard output.
- **FR-002**: The command MUST exit with success whenever a graph is produced, even if it contains
  unresolved imports or parse errors. It MUST exit with failure, and write no partial output file, when the
  input is invalid or over the limits.
- **FR-003**: The command MUST NOT write, modify or create anything inside the analyzed folder.

**Safety**

- **FR-004**: The analyzed project MUST be read only as text. No file from it is executed, imported, built
  or installed, and no tool configured by it is invoked.
- **FR-005**: Symbolic links MUST NOT be followed, and nothing outside the analyzed folder may be read.
- **FR-006**: The command MUST enforce three default limits, as constitution Principle I requires:
  - 5,000 non-skipped files;
  - 50 MB total size of non-skipped files;
  - 300 seconds of wall-clock time for the analysis.

  Users MUST be able to override all three. Exceeding any limit aborts the run with no output.

**Coverage**

- **FR-007**: Every file under the folder, except those in skipped folders, MUST appear in the coverage
  report exactly once. Each entry has its relative path, detected language (if any) and one status:
  `analyzed`, `detected_only` or `not_code`.
- **FR-008**: Language detection MUST use file extensions and marker files. In this slice only Python
  (`.py`, `.pyi`) gets `analyzed`. Other recognised programming languages get `detected_only`.
- **FR-009**: These folders MUST be skipped and listed with their reason: `.git`, `.venv`, `venv`, `env`,
  `node_modules`, `__pycache__`, `site-packages`, `dist`, `build`, `.tox`, `.mypy_cache`,
  `.pytest_cache`.

**Graph content**

- **FR-010**: The graph MUST contain one node per analyzed Python file, one node per distinct external
  top-level package that is imported, and one placeholder node per distinct unresolved reference
  (FR-014a). File nodes are identified by relative POSIX path. External nodes
  carry a kind: `stdlib` or `third_party`.
- **FR-010a**: Each file node MUST carry a list of its definitions: module-level classes and functions, and
  methods of those classes. Each definition has a kind (`class`, `function` or `method`), a qualified name
  (for example `AuthService.login`) and a 1-based line. The list is sorted by line, then by qualified name.
  Definitions are not separate nodes and have no edges in this slice.
- **FR-011**: The standard-library classification MUST come from a fixed list shipped with the extractor
  version. It MUST NOT depend on the Python installation that runs the tool.
- **FR-012**: The graph MUST contain one `imports` edge per import statement and imported name. This covers
  `import x`, `import x as y`, `from x import y`, relative `from . import y`, and dynamic imports via
  `importlib.import_module` and `__import__`.
- **FR-013**: Every edge MUST carry: source, target, type, imported symbol (when present), 1-based line,
  snapshot id, confidence, extractor name@version, and a hash of the normalized import statement text.
  An edge missing any of these MUST NOT be emitted.
- **FR-014**: Confidence MUST be `resolved` when the target is determined by the resolution rules (a local
  file or an external package). It MUST be `unresolved` when it is not. No edge in this slice is
  `heuristic`.
- **FR-014a**: An unresolved edge MUST point to a placeholder node with id `unresolved:<reference>`. The
  reference is:
  - the absolute dotted module name, for relative imports whose base package can be computed (for example
    `unresolved:pkg.missing`);
  - otherwise, the import expression exactly as written (for example
    `unresolved:importlib.import_module(name)` or `unresolved:...x`).

  Edges with the same reference share one placeholder node. Placeholder nodes have kind `unresolved`.
- **FR-015**: Resolution MUST search these source roots in this order: the analyzed folder itself, then
  `src/` if it exists. A local match MUST win over an external classification. Absolute imports that match
  no local module MUST be classified as external, unless their top-level name is a module or package that
  exists only below the roots (for example `backend/app/` in a monorepo, imported as `app`) and is not a
  standard-library name: such imports MUST be `unresolved` with reason `not_found`, because the subproject's
  own root is not known. Relative imports and dynamic imports that match no local module MUST be `unresolved`.

**Snapshot and determinism**

- **FR-016**: The snapshot id MUST be:
  - the HEAD commit SHA, when the folder is the root of a clean git working tree;
  - `<sha>+dirty:<content-hash>`, when that tree has uncommitted changes;
  - `content:<content-hash>` of the included files, when the folder is not a git working-tree root.

  The content hash covers every included file's relative path and bytes, in sorted path order.
- **FR-016a**: This feature's PR MUST include a PATCH amendment to constitution Principle III that adds the
  `content:<hash>` snapshot id form.
- **FR-017**: The output MUST be byte-identical for the same snapshot and extractor versions. Nodes, edges,
  coverage entries and object keys are emitted in a defined sorted order. The output uses UTF-8 and LF line
  endings, ends with a single trailing newline, and contains no timestamps, absolute paths or host-specific
  values.

**Schema**

- **FR-018**: The output MUST validate against `schema/graph.schema.json` at schema version 1. The output
  MUST state that schema version.
- **FR-019**: The schema MUST define nodes, edges with provenance, the confidence levels, the coverage
  report and the snapshot id. It MUST be strict enough to reject an edge without provenance.

**Ground truth**

- **FR-020**: At least three fixture repositories MUST exist in `fixtures/repos/`, each with a hand-checked
  `expected.json`. Together they MUST cover:
  - absolute imports and relative imports, including above-top-level;
  - a `src/` layout with tests importing the package;
  - a namespace package;
  - an import cycle;
  - stdlib and third-party external packages;
  - a dynamic import with a variable argument and one with a literal argument;
  - a file with a syntax error;
  - classes with methods, and module-level functions;
  - non-Python files and a skipped virtual-environment folder.
- **FR-021**: Automated tests MUST check each fixture's output against its `expected.json`, check that
  repeated runs give identical bytes, and validate the output against the schema.

### Key Entities

- **Snapshot**: the exact project state that was analyzed, identified by the snapshot id.
- **File node**: an analyzed Python file, identified by its path relative to the analyzed folder. It
  carries its list of definitions.
- **Definition**: a class, function or method declared in a file node, with its qualified name and line.
  It is an attribute of the file node, not a node of its own.
- **External package node**: an imported top-level package not found locally. Its kind is `stdlib` or
  `third_party`.
- **Unresolved node**: a placeholder node, `unresolved:<reference>`, for an import whose target could not
  be determined. It is shared by all edges with the same reference (FR-014a).
- **Import edge**: one import statement (and imported name) from a file node to a target, with full
  provenance and a confidence level.
- **Coverage file**: a walked, non-skipped file with its language, status and flags (`parse_error`,
  `unreadable`).
- **Skipped entry**: a skipped folder or file with its reason (`excluded_dir`, `nested_repository`,
  `symlink`, `minified`).
- **Graph document**: the schema version, snapshot id, extractor versions, nodes, edges and coverage
  report, as one file.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On every fixture repository, 100% of hand-checked edges and nodes are reproduced, and no
  unexpected edge or node appears.
- **SC-002**: The analysis makes zero guesses. Every import in the fixtures that the documented rules cannot
  resolve is reported as `unresolved`, never as a wrong file.
- **SC-003**: 10 consecutive runs on each fixture, from two different absolute paths, produce byte-identical
  output.
- **SC-004**: 100% of files in each fixture are accounted for in the coverage report, either as an entry or
  under a skipped folder.
- **SC-005**: A project with about 1,000 Python files is analyzed in under 30 seconds on a typical developer
  laptop.
- **SC-006**: A teammate who has never seen the code can trace any edge in the output back to the exact
  source line in under one minute, using only the edge's provenance.

## Assumptions

- The input is a local folder supplied by the user. Downloading from GitHub, ZIP import and archive-extraction
  protection belong to the next slice, `002`.
- Nodes are files and external packages only. Separate class and function nodes, and symbol-level edges, are
  deferred to a later slice. Definitions are already listed on file nodes (FR-010a), and the imported name
  is recorded on each edge.
- External packages are identified by their top-level import name. Mapping that name to a distribution name
  (for example `yaml` to `PyYAML`) is out of scope.
- Source roots are fixed to the analyzed folder and `src/`. Reading custom roots from project configuration
  files is out of scope for this slice.
- The `content:<hash>` snapshot form for non-git folders is needed because the fixtures live inside the
  Graphora repository, not in repositories of their own. It is added to the constitution by a PATCH
  amendment (FR-016a).
- No database, HTTP API, UI, MCP server, graph queries (cycles, impact, centrality) or language model are
  part of this slice. The cycle requirement is met by both edges being present in the graph.
