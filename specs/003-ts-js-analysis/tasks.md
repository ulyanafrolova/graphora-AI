---

description: "Task list for 003-ts-js-analysis"
---

# Tasks: TypeScript/JavaScript Analysis (Graph Schema v2)

**Input**: Design documents from `specs/003-ts-js-analysis/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/graph.schema.json,
contracts/cli.md, quickstart.md

**Tests**: Required. FR-023, FR-024 and constitution Principle VIII require golden, determinism and schema
tests. Within each story, write the tests first and confirm they fail before you implement.

**Organization**: Tasks are grouped by user story:

- US1 (P1): the TS/JS import graph (imports, `require`, `import()`, definitions, resolution);
- US2 (P2): barrel files (re-export edges, full export information, workspace packages);
- US3 (P3): mixed repositories and ecosystem separation.

Schema v2 and the Python migration are foundational, because nothing can emit TS/JS nodes before the
schema allows them, and the existing golden tests must stay green from the first commit onward.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: The user story the task belongs to (US1, US2 or US3)

Paths are relative to the repository root. Python code lives in `backend/src/graphora/`, tests in
`backend/tests/` and fixtures in `fixtures/repos/`. Run commands from `backend/`.

---

## Phase 1: Setup

**Purpose**: Dependencies and the shipped built-in list.

- [ ] T001 Add `tree-sitter-typescript==0.23.2` and `tree-sitter-javascript==0.25.0` to `dependencies` in
  `backend/pyproject.toml`, keeping the existing exact pins. Run `uv sync` in `backend/` and commit the
  updated `backend/uv.lock`.
- [ ] T002 [P] Create `backend/src/graphora/resolve/data/node_builtins.txt` (research R6):
  - one name per line, sorted, UTF-8, LF;
  - the union of `require("module").builtinModules` for Node 20, 22 and 24, top-level names only (`fs`,
    not `fs/promises`; `fs/promises` resolves through its top segment);
  - prefix-only modules on lines of the form `node:<name>`: `node:sea`, `node:sqlite`, `node:test`,
    `node:test/reporters`;
  - a first comment line `# node-builtins@24.0.0`.
- [ ] T003 [P] Create `backend/scripts/gen_node_builtins.py`. It runs a local `node -p` to print
  `builtinModules` and rewrites `node_builtins.txt` in the T002 format, merging with the existing file so
  the union is kept. Add a module docstring stating that it needs a local Node, is never run by tests or by
  `analyze`, and reads nothing from analyzed repositories.

---

## Phase 2: Foundational (schema v2 and Python migration)

**Purpose**: Schema v2, the model and serializer changes, and the migration of the Python output and its
fixtures. After this phase the existing 001 test suite passes on v2, before any TS/JS code exists.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 [P] Copy `specs/003-ts-js-analysis/contracts/graph.schema.json` to `schema/graph.schema.json`,
  replacing v1.
- [ ] T005 [P] Rewrite `backend/tests/contract/test_schema.py` for v2:
  - **Valid cases**: a Python-only document and a TS document, both built through `to_dict` from model
    objects. The TS document must contain an asset node, an npm external node, a `reexports` edge with an
    `alias`, and a file node with `exports`.
  - **Rejected cases**, one test each:
    - an edge without `snippet_hash`;
    - an edge without `form`;
    - an edge without `type_only`;
    - `alias` on an `imports` edge;
    - a `reexports` edge with `form: "dynamic"`;
    - an unresolved edge without `reason`;
    - a resolved edge whose target starts with `unresolved:`;
    - a TS file node without `exports`;
    - a TS definition without `exported_as`;
    - a Python definition with `exported_as`;
    - a Python definition with kind `interface`;
    - a Python file node with `exports`;
    - an npm external node with category `stdlib`;
    - an external node with `ecosystem: "python"` and id `ext:npm:os`;
    - a v1 id `ext:react`;
    - an unresolved node without `ecosystem`;
    - `schema_version: 1`;
    - a node `path` of `../x.ts`.
- [ ] T006 [P] Update `backend/tests/unit/test_serialize.py` for v2. It must assert:
  - `schema_version` is `2`;
  - edges sort by `(source, line, column, target, symbol ?? "", alias ?? "", type)`;
  - edge `id` is `"e:" + sha256("source|line|column|target|symbol|alias|type")[:16]`, with `""` for
    null values;
  - two edges differing only in `alias` get different ids;
  - `form` and `type_only` are always written, and `alias` is written only when set;
  - a Python file node has neither `exports` nor `exported_as` on its definitions;
  - a TS file node always has `exports` (possibly `[]`), and each definition has `exported_as`, sorted and
    unique;
  - `exports` are sorted by `(name, line)`;
  - external and unresolved nodes include `ecosystem`, and ids are `ext:<ecosystem>:<name>` and
    `unresolved:<ecosystem>:<reference>`;
  - an asset node serializes as `{"id": "asset:<path>", "kind": "asset", "path": <path>}`;
  - the existing determinism and byte-format assertions still hold.
- [ ] T007 Update `backend/src/graphora/graph/model.py` (data-model.md § Node, § Edge):
  - add the `Ecosystem = Literal["python", "npm"]` and `Form = Literal["static", "dynamic", "require"]`
    types, and `EdgeType = Literal["imports", "reexports"]`;
  - add `"workspace_package"` to `Reason` and `"interface" | "type_alias" | "enum"` to `DefinitionKind`;
  - set `Category = Literal["stdlib", "builtin", "third_party"]`;
  - add `Definition.exported_as: tuple[str, ...] | None = None` (None for Python);
  - add `Export(name: str, local: str | None, line: int)`;
  - set `FileNode(path, language, definitions=(), exports=None)`, with `exports` None for Python;
  - set `ExternalNode(name, ecosystem, category)` with id `ext:<ecosystem>:<name>`, and
    `UnresolvedNode(reference, ecosystem)` with id `unresolved:<ecosystem>:<reference>`;
  - add `AssetNode(path)` with id `asset:<path>`, and include it in `Node`;
  - add the `Edge` fields `type: EdgeType = "imports"`, `form: Form = "static"`, `type_only: bool = False`
    and `alias: str | None = None`. In `__post_init__` also raise when `alias` is set on a non-`reexports`
    edge, or when a `reexports` edge has a form other than `static`;
  - update the module docstring to point to `specs/003-ts-js-analysis/data-model.md` as well.
- [ ] T008 Update `backend/src/graphora/graph/serialize.py`:
  - `SCHEMA_VERSION = 2`;
  - the new `edge_id` and `edge_sort_key` from T006;
  - `_node_dict` for every node kind, with `language` taken from the node (no hard-coded `"python"`);
  - `_edge_dict` writes `type`, `form` and `type_only` always, and `alias` only when set.

  Make T005 and T006 pass.
- [ ] T009 Update `backend/src/graphora/resolve/python.py` so it returns ids `ext:python:<top>` and
  `unresolved:python:<reference>`, without changing any rule. Update `backend/tests/unit/test_resolve.py`
  to the new ids only.
- [ ] T010 Create `backend/src/graphora/adapters/js/__init__.py` with only the constants
  `NAME = "js-adapter"`, `VERSION = "0.1.0"` and `EXTRACTOR`, and add `RESOLVER_VERSION = "0.1.0"` plus
  `BUILTINS_VERSION = "24.0.0"` constants in a new `backend/src/graphora/resolve/js.py`, which holds only
  these constants for now. Bump `backend/src/graphora/adapters/python/__init__.py` to `VERSION = "0.2.0"`
  and `RESOLVER_VERSION` in `backend/src/graphora/resolve/python.py` to `"0.2.0"`, because its node ids
  change.
- [ ] T011 Update `backend/src/graphora/graph/build.py` for the v2 model with Python only:
  - construct `FileNode(path, "python", definitions)`, `ExternalNode(name, "python", category)` and
    `UnresolvedNode(reference, "python")` from the `ext:python:` / `unresolved:python:` target ids;
  - set the edge `form` to `"dynamic"` for records with `kind == "dynamic"`, else `"static"`, with
    `type_only=False`;
  - write all six `extractors` keys from data-model.md § GraphDocument: `js-adapter`, `js-resolver`,
    `node-builtins`, `python-adapter`, `python-resolver`, `python-stdlib`.
- [ ] T012 Update `project()` in `backend/tests/conftest.py` (research R9):
  - nodes: add `ecosystem` for external and unresolved nodes, `path` for asset nodes, and for file nodes
    `language` plus, when present, `exports`. Definitions are copied as serialized, so TS definitions
    include `exported_as`;
  - edges: add `type` and `form` always, `type_only` only when `true`, and `alias` only when set;
  - the edge sort key in `project()` and in `_normalize` of `backend/tests/golden/test_fixtures.py`
    becomes `(source, line, target, symbol or "", alias or "", type)`.
- [ ] T013 Migrate by hand `fixtures/repos/py-flat/expected.json`, `fixtures/repos/py-src-layout/expected.json`
  and `fixtures/repos/py-dynamic/expected.json` to the T012 projection:
  - prefix ids: `ext:x` → `ext:python:x`, `unresolved:r` → `unresolved:python:r`, in nodes and in edge
    targets;
  - add `"ecosystem": "python"` to those nodes and `"language": "python"` to file nodes;
  - add `"type": "imports"` to every edge, and `"form": "static"` or, for `importlib.import_module` /
    `__import__` edges, `"form": "dynamic"`.

  Change nothing else (FR-020). The `web/app.ts` change in `py-dynamic` belongs to T033.
- [ ] T014 In `backend/tests/golden/test_fixtures.py`:
  - change `test_provenance_consistent` to expect `python-adapter@0.2.0` for edges from `.py` / `.pyi`
    sources and `js-adapter@0.1.0` for all others;
  - before editing anything in T013, copy the three v1 files once with
    `git show 732e98c:fixtures/repos/<name>/expected.json > backend/tests/golden/v1/<name>.json`, and commit
    them as frozen test data. Add a README line in `backend/tests/golden/v1/` saying they are the v1 ground
    truth from feature 001 and must never be edited. The test reads these files, with no git access at test
    time, so it survives a squash merge of 001 and shallow CI clones;
  - add `test_python_fixtures_match_v1`, for `py-flat`, `py-src-layout` and `py-dynamic`. It loads
    `backend/tests/golden/v1/<name>.json` and maps the v2 projection back to v1:
    - strip the `python:` part of the ids;
    - drop `type`, `form`, `ecosystem` and `language`;
    - keep only Python-language file nodes and edges with Python sources.

    It asserts that the v1 nodes and edges are equal (SC-003).
- [ ] T015 Run `uv run pytest -m "not slow"`. Every existing test must pass on schema v2 before Phase 3
  starts.

**Checkpoint**: v2 schema in place, Python output migrated, 001 test suite green.

---

## Phase 3: User Story 1 - TS/JS import graph (Priority: P1) 🎯 MVP

**Goal**: TS/JS files are analyzed. Every import, `require`, `import()` and `import x = require()` is an
edge with provenance, resolved by the data-model rules.

**Independent Test**: `ts-app` and `js-commonjs` fixtures match their `expected.json`, are deterministic and
validate against v2 (quickstart § 2, § 3).

**Scope rule for this phase**: export information in US1 comes only from `export` on a declaration
(`export class C`, `export function f`, `export const f = () => …`, `export const x = 1`). `export { … }`,
`export default` and `export … from` are US2. The US1 fixtures must therefore not contain them.

### Tests for User Story 1

- [ ] T016 [P] [US1] Update `backend/tests/unit/test_languages.py`:
  - `.ts`, `.tsx`, `.mts`, `.cts` and `x.d.ts` give `("typescript", "analyzed")`;
  - `.js`, `.jsx`, `.mjs` and `.cjs` give `("javascript", "analyzed")`;
  - `.vue`, `.svelte` and `.astro` give `detected_only` with languages `vue`, `svelte` and `astro`;
  - `jsconfig.json` is a marker with language `javascript` and status `not_code`;
  - replace the `DETECTED_ONLY_EXTENSIONS` table test with the new table, which has no TS/JS entries and
    does have the three new ones.
- [ ] T017 [P] [US1] Extend `backend/tests/unit/test_walk.py` so each of `.next`, `.nuxt`, `.turbo`,
  `.svelte-kit`, `coverage`, `out` and `bower_components` is skipped once with reason `excluded_dir`, and
  its contents are not listed.
- [ ] T018 [P] [US1] Write `backend/tests/unit/test_js_extract.py`. Assert on records and definitions
  returned for small sources:
  - **Import forms**, each row of research R2 except the `export … from` rows: symbol, form, type-only,
    line and column;
  - inline `import { type A, B }` gives `A` type-only and `B` not;
  - `import x, { a } from "m"` gives two records, `default` and `a`;
  - a `require` with two arguments is ignored, and so is `obj.require("x")`;
  - **Literal detection**: `` require(`./a`) `` is a literal, while `` require(`./${a}`) ``,
    `require("./a" + b)` and `require(name)` are dynamic, with the record text equal to the call text;
  - `require` and `import()` inside functions and nested blocks are recorded;
  - **Columns** are counted in Unicode code points, for a line that starts with a non-ASCII string;
  - the **snippet text** is the whole statement for static imports and the call for `require` and
    `import()`;
  - **Definitions**, every row of the data-model.md definition table except `export default`:
    - `function_signature` overloads collapse to the first line;
    - a getter/setter pair gives one `method`;
    - nested functions, namespaces, class fields and abstract signatures are not listed;
    - the line is the keyword line when a decorator sits on the line above;
  - **`exported_as`**: `["C"]` for `export class C`, `[]` for an unexported class, and `export const x = 1`
    gives `Export("x", "x", line)`;
  - **Grammar choice**: JSX in a `.tsx` and a `.jsx` file has no parse error, while JSX in a `.ts` file
    sets `has_error`;
  - a file with a syntax error still yields its intact imports;
  - a UTF-8 BOM is stripped, and invalid UTF-8 returns None (`unreadable`).
- [ ] T019 [P] [US1] Write `backend/tests/unit/test_tsconfig.py` (research R4):
  - **JSONC**: `//` and `/* */` comments are stripped, but not inside strings (`"a//b"`); trailing commas
    in objects and arrays are dropped; a non-object or invalid input returns None;
  - **Nearest config**: the nearest ancestor wins, `tsconfig.json` beats `jsconfig.json` in the same
    folder, and nothing above the root is considered;
  - **`extends`**:
    - a string, and an array where later entries override earlier ones;
    - `./base` resolves to `./base.json`;
    - a package name, an absolute path and `../../outside.json` above the root are ignored;
    - a skipped path is ignored;
    - a cycle stops at the first repeat;
  - **Anchoring**: `baseUrl` is relative to the defining config; `paths` are relative to the effective
    `baseUrl`, or to the folder of the config that defines `paths` when there is no `baseUrl`;
  - **Broken configs** (data-model.md § Coverage):
    - every loaded config that cannot be read as JSONC is reported in `Configs.invalid`, whether or not
      any file uses it;
    - a file whose nearest config is broken uses the next valid ancestor config, as if the broken one were
      absent;
    - a broken `extends` target is skipped, and the remaining chain still applies.
- [ ] T020 [P] [US1] Write `backend/tests/unit/test_js_resolve.py`, one test per row of the
  data-model.md resolution table, using in-memory file sets:
  - **`try()` order**: exact file, then the extensions in the order "`.ts`, `.tsx`, `.d.ts`, `.mts`,
    `.cts`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.json`", then `.js` → `.ts` / `.tsx`, `.jsx` → `.tsx`,
    `.mjs` → `.mts`, `.cjs` → `.cts`, then `index` plus each extension;
  - `./foo` where `foo/` is a folder and `foo.ts` exists resolves to `foo.ts`;
  - a match on a non-analyzed file gives `asset:`, and a match on an analyzed file gives `file:`;
  - a missing relative path is `not_found` with the normalized path as reference (`src/missing`);
  - `../` above the root is `not_found` with the specifier as written;
  - `/x`, `https://x`, `data:x` and `#internal` are `not_found` with the specifier as written;
  - `node:fs`, `fs` and `fs/promises` all give `ext:npm:fs` with category `builtin`;
  - `node:test` gives a builtin, bare `test` gives a third-party package, and `node:nope` is `not_found`;
  - **`paths`**: an exact pattern beats `*`, and the longest prefix wins; listed targets are tried in
    order; a matched pattern with no file is `not_found`, and later patterns are not tried;
  - **`baseUrl`**: a hit resolves, and a miss falls through to npm (`react` gives `ext:npm:react`);
  - **Package names**: `@scope/pkg/deep` gives `ext:npm:@scope/pkg`; `lodash/fp` gives
    `ext:npm:lodash`; `@scope` and `@scope/` are `not_found`;
  - a dynamic record is `unresolved` with reason `dynamic` and the call text as reference.
- [ ] T021 [P] [US1] Create the fixture `fixtures/repos/ts-app/repo/` and hand-write
  `fixtures/repos/ts-app/expected.json` (all sections: `snapshot_kind`, `nodes`, `edges`, `coverage`,
  `skipped`). The fixture must contain (plan.md § Source Code):
  - `tsconfig.json` with comments, extending `./tsconfig.base` (no `.json`). The base sets
    `"baseUrl": "."` and paths `{"@app/*": ["src/*"], "@lib": ["src/lib/index.ts"]}`;
  - an entry file `src/main.ts` (quickstart § 2 queries it), with relative imports, a folder import
    resolving to `index.ts`, `./util.js` resolving to `util.ts`, and a `.d.ts` file;
  - default, named, namespace, side-effect, `import type` and inline-`type` imports;
  - `import fs = require("fs")`, `node:fs`, `fs/promises`, `@scope/pkg/deep` and `react`;
  - existing `./styles.css` and `./data.json` imports (asset nodes), and a missing `./logo.svg`;
  - a missing relative import, a missing `@app/missing` alias, and a `baseUrl` import (`src/config`);
  - a two-file import cycle;
  - a `.tsx` component with JSX and a decorated class;
  - a `.ts` file with a syntax error;
  - a `.vue` file;
  - `node_modules/react/index.js`, `dist/bundle.js` and `.next/cache.js`, all skipped.
- [ ] T022 [P] [US1] Create the fixture `fixtures/repos/js-commonjs/repo/` and hand-write its
  `expected.json`. The fixture must contain:
  - `require` with a literal, with a non-literal argument, and with a template literal without
    substitutions;
  - `` import(`./p/${n}`) `` inside a function;
  - `.mjs` and `.cjs` files;
  - `jsconfig.json` with `paths`;
  - `node:test` and bare `test`;
  - a `#internal` import, a `https://` import, and `../../outside` above the root;
  - a second, broken `jsconfig.json` in a subfolder, expected with the `parse_error` flag;
  - `vendor/lib.min.js`, skipped as `minified`.

### Implementation for User Story 1

- [ ] T023 [P] [US1] Update `backend/src/graphora/detect/languages.py` (data-model.md § Coverage):
  - move the TS/JS extensions into `ANALYZED_EXTENSIONS`;
  - add `.vue`, `.svelte` and `.astro` to `DETECTED_ONLY_EXTENSIONS`;
  - add the marker `jsconfig.json` → `javascript`.

  Make T016 pass.
- [ ] T024 [P] [US1] Add `.next`, `.nuxt`, `.turbo`, `.svelte-kit`, `coverage`, `out` and
  `bower_components` to `EXCLUDED_DIRS` in `backend/src/graphora/ingest/walk.py`. Make T017 pass.
- [ ] T025 [US1] Implement `backend/src/graphora/adapters/js/extract.py`, part 1: imports.
  - Load the grammars per research R1 and pick one by file extension.
  - Expose `extract(path: str, source: bytes) -> FileFacts | None`, returning None for invalid UTF-8 and
    stripping a BOM.
  - Return a JS `ImportRecord` with `kind` (`static` / `require` / `dynamic`), `specifier` (or None when
    dynamic), `names` (tuples of `(symbol, type_only)`), `text`, `line`, `column` and `literal`.
  - Cover every row of research R2 except the `export … from` rows.
  - `has_error` is true when the tree contains ERROR or MISSING nodes.
- [ ] T026 [US1] Implement `backend/src/graphora/adapters/js/extract.py`, part 2: definitions, following
  the data-model.md definition table and the line rule "Line of the declaring keyword … never of a
  decorator". Fill `exported_as` from `export` declarations only, and add `Export(name, name, line)` for
  exported declarations that are not definitions (`export const x = 1`). Make T018 pass.
- [ ] T027 [P] [US1] Implement `backend/src/graphora/resolve/tsconfig.py`:
  - `parse_jsonc(text) -> dict | None`;
  - `load_configs(files: set[str], read: Callable[[str], bytes]) -> Configs`, which loads every
    `tsconfig.json` and `jsconfig.json` in `files`, plus every file reached through their `extends` chains
    inside the root (for example `tsconfig.base.json`). It reads nothing else;
  - `Configs.for_file(path) -> Effective(base_url: str | None, paths: tuple[tuple[str, tuple[str, ...]], ...])`,
    with `paths` already ordered "an exact pattern first, then the longest prefix before `*`";
  - `Configs.invalid: tuple[str, ...]`, sorted.

  Cache the effective config per folder. Make T019 pass.
- [ ] T028 [US1] Implement `backend/src/graphora/resolve/js.py` (keep the T010 constants):
  - load `node_builtins.txt` once;
  - `try_path(p, files, analyzed)`, implementing the resolution table except the workspace row;
  - `resolve(path, record, files, analyzed, configs) -> list[Target]`, with one target per name, using
    `file:`, `asset:`, `ext:npm:` and `unresolved:npm:` ids;
  - a `category(name)` helper giving `builtin` or `third_party`;
  - cache `try_path` per candidate path.

  Make T020 pass, except the workspace cases added in US2.
- [ ] T029 [US1] Update `backend/src/graphora/graph/build.py`:
  - dispatch by coverage language: Python to the Python adapter and resolver, `typescript`/`javascript` to
    the JS adapter and resolver;
  - build `Configs` from the walked files, and add `parse_error` to the coverage flags of
    `Configs.invalid` paths;
  - create `AssetNode`s for `asset:` targets and `ExternalNode(name, "npm", category)` /
    `UnresolvedNode(reference, "npm")` for npm targets;
  - set `FileNode(path, language, definitions, exports)`, with `exports=()` for TS/JS files without
    exports;
  - set `form` and `type_only` from the record, and `extractor` to `js-adapter@0.1.0`;
  - return the invalid config paths alongside the document as warnings, for example
    `build(...) -> tuple[GraphDocument, tuple[str, ...]]`, and update the callers.
- [ ] T030 [US1] In `backend/src/graphora/cli/__init__.py`, log
  `graphora: warning: ignoring <path>: not valid JSON-with-comments` for each warning returned by `build`,
  before the summary line (contracts/cli.md). Add a test to `backend/tests/integration/test_cli.py`: a
  broken `tsconfig.json` gives exit `0`, the warning line on stderr, and `parse_error` in coverage.
- [ ] T031 [US1] Extend `backend/tests/integration/test_safety.py` with a TS case, built in `tmp_path`:
  - a `tsconfig.json` that `extends` `../outside.json`, where `outside.json` exists next to the repository
    and sets `"paths": {"@out/*": ["src/*"]}`, and a file `src/x.ts` imported as `@out/x`;
  - a `node_modules/pkg/index.js` that writes a marker file if executed;
  - a `package.json` with `"scripts": {"postinstall": "touch MARKER"}`.

  Monkeypatch `subprocess.Popen`, `os.system` and `os.posix_spawn` to fail the test if called. Assert:
  - exit `0`;
  - no marker file;
  - the `@out/x` edge targets `ext:npm:@out/x` and not `file:src/x.ts`. The outside config was not read,
    so the specifier falls through to npm (data-model.md § Resolution);
  - the repository tree is unchanged.
- [ ] T032 [US1] Run the golden tests for `ts-app` and `js-commonjs`. Fix the implementation, never
  `expected.json`, unless a hand-check against data-model.md shows that the expected file is wrong. Record
  any such correction in the commit message.
- [ ] T033 [US1] Update `fixtures/repos/py-dynamic`:
  - in `expected.json`, `web/app.ts` becomes `analyzed` with the file node
    `{"id": "file:web/app.ts", "kind": "file", "language": "typescript", "definitions": [], "exports": [{"name": "x", "local": "x", "line": 1}]}`;
  - add `repo/tools/main.go` (one line, `package main`) and its coverage entry `detected_only` / `go`, so
    the `detected_only` status stays covered (spec FR-020).

  Confirm that `test_python_fixtures_match_v1` still passes.

**Checkpoint**: US1 is fully functional. `uv run pytest -m "not slow"` is green, and quickstart § 2 and
§ 3 hold.

---

## Phase 4: User Story 2 - Barrel files (Priority: P2)

**Goal**: Re-exports are edges, every exported name is recorded once, and workspace packages are honestly
`unresolved`.

**Independent Test**: the `ts-monorepo` fixture matches `expected.json`. Following `imports` →
`reexports` → `exported_as` from the app's `Logger` import reaches `packages/ui/src/log.ts` using only the
JSON (quickstart § 4, SC-006).

### Tests for User Story 2

- [ ] T034 [P] [US2] Extend `backend/tests/unit/test_js_extract.py`:
  - the `export … from` rows of research R2: `export *`, `export * as ns` (symbol `*`, alias `ns`),
    `export { a, b as c } from` (alias only on `b`), and `export type { T } from` (type-only), all with
    edge type `reexports` and form `static`;
  - `export { a as b, a as c } from "./x"` gives two records with different aliases;
  - local `export { f }` and `export { f as g }` add to `f.exported_as`;
  - `export default class C` adds `default` to `C`;
  - anonymous `export default function () {}` gives a definition named `default`;
  - `export default router` gives `Export("default", "router", line)`, and `export default { … }` gives
    `Export("default", None, line)`;
  - `import { a } from "./m"; export { a as b }` gives `Export("b", "a", line)`;
  - the invariant "every name a TS/JS file exports appears exactly once" holds over a file combining all
    of the above.
- [ ] T035 [P] [US2] Extend `backend/tests/unit/test_js_resolve.py` with the workspace row:
  - a nested `packages/ui/package.json` with `"name": "@acme/ui"` makes `@acme/ui` and `@acme/ui/button`
    `unresolved` with reason `workspace_package` and the specifier as reference;
  - the root `package.json` name is not a workspace name;
  - two packages declaring the same name are still workspace names;
  - a `paths` alias for the same name still wins (it comes first);
  - a `package.json` that is not valid JSON contributes no name and gets no coverage flag (data-model.md
    § Resolution).
- [ ] T036 [P] [US2] Create the fixture `fixtures/repos/ts-monorepo/repo/` and hand-write its
  `expected.json`. The fixture must contain:
  - a root `package.json` with `workspaces`;
  - `packages/ui/package.json` (`"name": "@acme/ui"`) and its own `tsconfig.json`;
  - a barrel `packages/ui/src/index.ts` with `export * from "./math"`,
    `export { Log as Logger } from "./log"`, `export * as fmt from "./format"` and
    `export type { Level } from "./types"`;
  - in `log.ts`: `export class Log`, a private `function format`, and a local `export { format as fmt2 }`;
  - in `math.ts`: overloads, `export default function`, `export const PI = 3.14` and
    `import { x } from "./x"; export { x }`;
  - `packages/app/` with its own `tsconfig.json`, importing `@acme/ui` (workspace) and
    `../../ui/src` (the barrel by relative path, `Logger`).

  The expected edges must contain no edge from `packages/app/…` to `packages/ui/src/log.ts` (FR-007b).

### Implementation for User Story 2

- [ ] T037 [US2] Extend `backend/src/graphora/adapters/js/extract.py` with `export … from` statements:
  - each becomes a record with edge type `reexports`, form `static`, `symbol` (the name in the target,
    or `*`) and `alias` (the exported name when it differs, or the namespace name for `export * as ns`);
  - extend `ImportRecord.names` to `(symbol, type_only, alias)`.
- [ ] T038 [US2] Extend `backend/src/graphora/adapters/js/extract.py` with local export lists and
  `export default`, filling `exported_as` and `exports` exactly as described in data-model.md § "How
  `exported_as` is filled" and § Export. Make T034 pass.
- [ ] T039 [US2] Add the workspace step to `backend/src/graphora/resolve/js.py`, between `baseUrl` and the
  built-ins: compute `W` from every non-root `package.json` in the walked files (reading only `name`, and
  ignoring invalid JSON). Pass the edge type and alias through `backend/src/graphora/graph/build.py` into
  `Edge`. Make T035 pass.
- [ ] T040 [US2] Add `test_exports_invariant` to `backend/tests/golden/test_fixtures.py`. For every TS/JS
  file node in every fixture, count each exported name across `definitions[].exported_as`, `exports[].name`
  and the `alias` or `symbol` (except `*` without alias) of its `reexports` edges, and assert that each
  count is 1.
- [ ] T041 [US2] Run the golden tests for `ts-monorepo`, under the same rule as T032.

**Checkpoint**: US1 and US2 both pass, and quickstart § 4 holds.

---

## Phase 5: User Story 3 - Mixed repositories (Priority: P3)

**Goal**: One graph for a Python + TS repository, with separate ecosystems and no cross-language edges.

**Independent Test**: the `mixed-fullstack` fixture matches `expected.json`. `ext:python:yaml` and
`ext:npm:yaml` are both present (quickstart § 5). The Python fixtures pass the v1-equivalence test
(quickstart § 6).

### Tests for User Story 3

- [ ] T042 [P] [US3] Create the fixture `fixtures/repos/mixed-fullstack/repo/` and hand-write its
  `expected.json`. The fixture must contain:
  - `backend/` with `pyproject.toml`, `app/__init__.py` and `app/api.py`, importing `yaml` and
    `requests`;
  - `frontend/` with `package.json`, `tsconfig.json`, `src/main.tsx` and `src/api.ts`, importing `yaml`
    and `react`;
  - a `README.md`.

  The Python files resolve under the folder root, because there is no `src/` at the root.
- [ ] T043 [P] [US3] Add `test_ecosystems_separate` to `backend/tests/golden/test_fixtures.py`, running
  over every fixture:
  - every `ext:` and `unresolved:` target's ecosystem matches its source file's language (`python` for
    Python, `npm` for TS/JS);
  - in `mixed-fullstack` no edge connects a Python file and a TS/JS file;
  - `coverage.summary.by_language` has both `python` and `typescript`.

### Implementation for User Story 3

- [ ] T044 [US3] Run the golden tests for `mixed-fullstack`, under the same rule as T032, and fix any issue
  in `backend/src/graphora/graph/build.py`, the most likely place for language-dispatch mistakes.

**Checkpoint**: all stories pass independently.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T045 [P] Extend `backend/tests/integration/test_performance.py` with a `@pytest.mark.slow` test
  (SC-005). It generates 10 folders with 100 `.ts` files each. Each file has three relative imports, one
  `paths` alias import through a root `tsconfig.json`, and an exported class with a method. The test
  asserts exit `0` and the summary line `analyzed 1000 files, 4000 edges (0 unresolved)`. The summary counts
  only `analyzed` files, so `tsconfig.json` is not included. It allows under 30 s.
- [ ] T046 [P] Update `CLAUDE.md` § Commands if the commands changed (they should not). Add one line under
  Key rules: "TS/JS config files are data: never run Node, never read `node_modules`."
- [ ] T047 Before opening the PR, check whether the feature 002 branch exists on `origin`. If it changed
  `schema/graph.schema.json` or `graph/`, rebase and fold its changes into v2 (research R10). Then run
  `uv run pytest`, the full suite including slow tests.
- [ ] T048 Run every step of `specs/003-ts-js-analysis/quickstart.md`. Record any mismatch as a fix in the
  implementation, or as a documented correction to the spec, and confirm the determinism test covers all 7
  fixtures.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: needs T001. T004–T006 run in parallel. T007 → T008 → T009/T010 → T011 →
  T012 → T013 → T014 → T015.
- **US1 (Phase 3)**: needs Phase 2 and T002.
- **US2 (Phase 4)**: needs US1's extractor (T025, T026), resolver (T028) and build (T029). It extends the
  same files, so it is not parallel with US1.
- **US3 (Phase 5)**: needs US1. It is independent of US2, so it can run in parallel with Phase 4.
- **Polish (Phase 6)**: needs all stories.

### Within Each User Story

- Tests and fixtures first (they must fail), then the implementation, then the golden run.
- `extract.py` part 1 → part 2. `tsconfig.py` is parallel to the extractor, and `js.py` needs
  `tsconfig.py`.

### Parallel Opportunities

- Phase 1: T002 and T003.
- Phase 2: T004, T005 and T006.
- US1: T016–T022 (all tests and both fixtures), T023, T024 and T027.
- US2: T034, T035 and T036.
- US3: T042 and T043, and the whole phase can run alongside US2.

---

## Parallel Example: User Story 1

```bash
# Tests and fixtures, together:
Task: "Write backend/tests/unit/test_js_extract.py"
Task: "Write backend/tests/unit/test_tsconfig.py"
Task: "Write backend/tests/unit/test_js_resolve.py"
Task: "Create fixtures/repos/ts-app/ and its expected.json"
Task: "Create fixtures/repos/js-commonjs/ and its expected.json"

# Independent implementation files, together:
Task: "Update backend/src/graphora/detect/languages.py"
Task: "Update backend/src/graphora/ingest/walk.py"
Task: "Implement backend/src/graphora/resolve/tsconfig.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 and Phase 2. Stop and confirm the 001 suite is green on v2 (T015).
2. Phase 3, US1. Stop and run quickstart § 2 and § 3.
3. This is already demo-able: a TS frontend shows up on the map with honest confidence.

### Incremental Delivery

1. Setup + Foundational: v2 everywhere, with Python unchanged in substance.
2. + US1: TS/JS graphs.
3. + US2: barrels and exports, for correct impact queries later.
4. + US3: the mixed-repository guarantee.
5. Polish: performance, docs and coordination with 002.

### Parallel Team Strategy

After US1, one person takes US2 (the extractor and resolver) and another takes US3 (fixture and tests).

---

## Notes

- Hand-write every `expected.json` from the source files and data-model.md, never from tool output
  (CLAUDE.md).
- Commit fixture folders that start with a dot, or are otherwise ignored (`node_modules/`, `.next/`,
  `dist/`), with `git add -f`.
- Commit after each task or logical group, and stop at any checkpoint to validate.
