# Feature Specification: TypeScript/JavaScript Analysis (Graph Schema v2)

**Feature Branch**: `003-ts-js-analysis`

**Created**: 2026-10-28

**Status**: Draft

**Input**: User description: "feature 003 (lets assume 002 is currently developed by other person) TS/JS analysis (v2 schema)"

## Clarifications

### Session 2026-10-28

- Q: Should the analysis add derived edges by following re-export chains through barrel files? → A: No. Only
  edges written in the code are recorded. Chain-following belongs to the graph-query layer. To make it exact,
  each definition records whether it is exported, and each file records its local `export { … }` names.
- Q: How are bare imports of local monorepo workspace packages handled? → A: They stay `unresolved` with the
  new reason `workspace_package`. Resolving them to local files is deferred to a later slice.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get a trustworthy import graph of a TypeScript/JavaScript project (Priority: P1)

A developer runs the existing `graphora analyze <dir>` command on a TypeScript or JavaScript project and
receives the same kind of graph that Python projects get today. Every TS/JS file is a node, every npm package
and Node built-in module that is imported is a node, and every import, `require`, dynamic `import()` and
re-export is an edge with full provenance and an honest confidence level.

**Why this priority**: The constitution promises full analysis for Python and TypeScript/JavaScript in the MVP.
Most target repositories have a TS/JS frontend. Without it, the map, the frontend ↔ backend bridge and the
agents only see half of the repository.

**Independent Test**: Run the command on each new TS/JS fixture repository and compare the output with its
hand-checked `expected.json`. All expected nodes and edges must be present, and nothing extra may appear.

**Acceptance Scenarios**:

1. **Given** `src/a.ts` with `import { f } from "./b"` on line 2 and a file `src/b.ts`, **When** analyzed,
   **Then** the graph has an edge `src/a.ts → src/b.ts` with symbol `f`, line 2, confidence `resolved`, the
   snapshot id, the TS/JS extractor name@version and a snippet hash.
2. **Given** `import x from "./lib"` where `./lib` is a folder that contains `index.ts`, **When** analyzed,
   **Then** the edge resolves to `lib/index.ts`.
3. **Given** a `tsconfig.json` with `baseUrl` and a `paths` alias `@app/*` → `src/*`, and a file importing
   `@app/util`, **When** analyzed, **Then** the edge resolves to `src/util.ts` (or the matching index file).
4. **Given** a CommonJS file with `const fs = require("fs")` and `const lodash = require("lodash")`, **When**
   analyzed, **Then** there is an edge to a Node built-in package node `fs` and an edge to a third-party
   package node `lodash`.
5. **Given** `import(\`./pages/${name}\`)` with a variable part, **When** analyzed, **Then** an edge with
   confidence `unresolved` and reason `dynamic` is recorded at that line, and no file is guessed.
6. **Given** a TypeScript ESM file with `import { g } from "./c.js"` where only `c.ts` exists, **When**
   analyzed, **Then** the edge resolves to `c.ts`.

---

### User Story 2 - Barrel files do not hide real dependencies (Priority: P2)

A developer analyzes a project where many modules import from `index.ts` barrel files (`export * from "./x"`,
`export { y } from "./y"`). The graph still shows which files really depend on which.

**Why this priority**: Barrel files are common in TS projects. If re-exports are not recorded, the graph
collapses into a few index files and dependency, cycle and impact answers become useless (project-context
§ 11).

**Independent Test**: Run on a barrel fixture and compare with its `expected.json`. Every re-export statement
appears as an edge, and imports through a barrel can be traced to the file that defines the imported name.

**Acceptance Scenarios**:

1. **Given** `lib/index.ts` with `export * from "./math"` and `export { Logger } from "./log"`, **When**
   analyzed, **Then** there are `reexports` edges `lib/index.ts → lib/math.ts` and
   `lib/index.ts → lib/log.ts` (symbol `Logger`).
2. **Given** `app.ts` with `import { Logger } from "./lib"`, **When** analyzed, **Then** the edge
   `app.ts → lib/index.ts` (symbol `Logger`) is present exactly as written. No derived edge
   `app.ts → lib/log.ts` is added.
3. **Given** `lib/log.ts` with `export class Logger` and a non-exported helper `format`, **When** analyzed,
   **Then** the definition `Logger` is marked exported and `format` is not, so a later query can follow
   `export * from "./log"` to `Logger` without guessing.

---

### User Story 3 - One graph for mixed repositories, in the new schema (Priority: P3)

A developer analyzes a repository with a Python backend and a TS frontend. One graph file contains both
languages, and the coverage report marks both as `analyzed`. Python and TS/JS graphs both use schema version 2,
and a Python package and an npm package with the same name never merge into one node.

**Why this priority**: Real Graphora targets are full-stack repositories. The frontend team consumes one
schema, so the version change has to happen once, for both languages, in one change (constitution VII).

**Independent Test**: Run on a mixed fixture with Python and TS files, and re-run all existing Python fixtures.
All outputs validate against schema version 2 and match their (updated) `expected.json`.

**Acceptance Scenarios**:

1. **Given** a repository with `backend/*.py` and `frontend/src/*.tsx`, **When** analyzed, **Then** both sets
   of files are file nodes, coverage marks them `analyzed`, and there are no edges between the two languages.
2. **Given** a Python file that imports `yaml` and a JS file that imports `yaml`, **When** analyzed, **Then**
   there are two distinct external nodes, one per ecosystem.
3. **Given** the existing Python fixtures, **When** analyzed after this feature, **Then** their outputs state
   schema version 2 and match their updated `expected.json`. Apart from the schema changes listed in FR-020,
   their nodes and edges are unchanged.

---

### Edge Cases

- **Relative specifier with no matching file** (`./missing`): `unresolved`, reason `not_found`. It is never
  turned into an npm package.
- **Bare specifier that matches a `paths` alias but no file**: `unresolved`, reason `not_found`. It is not
  turned into an npm package.
- **Scoped and deep package imports** (`@scope/pkg/sub/path`, `lodash/fp`): resolved to the package node
  `@scope/pkg` / `lodash`, with the full specifier kept in the snippet.
- **`node:` prefix** (`node:fs`) and plain built-in names (`fs`): both resolve to the same built-in node `fs`.
- **Type-only imports** (`import type { T } from "./t"`, `export type { T } from "./t"`): recorded as edges
  and marked type-only.
- **Side-effect imports** (`import "./polyfill"`): one edge with no symbol.
- **Namespace import** (`import * as ns from "./m"`) and **default import**: symbol `*` and `default`.
- **Import of a non-code file** (`./styles.css`, `./data.json`, `./logo.svg`) that exists: a resolved edge to
  an asset node for that path. If it does not exist: `unresolved`, reason `not_found`.
- **`require` or `import()` with a non-literal argument**, or a template literal with substitutions:
  `unresolved`, reason `dynamic`. A template literal without substitutions counts as a literal.
- **`require` shadowed or re-defined locally**: still recorded as a `require` edge; the extractor does not
  do data-flow analysis.
- **The same target imported twice in one file**: two edges, one per statement.
- **Import cycles** between TS/JS files: both edges are present.
- **JSX/TSX syntax and decorators**: parsed; definitions and imports are extracted as usual.
- **Syntax error in a TS/JS file**: listed as `analyzed` with a `parse_error` flag; imports from readable
  parts are kept.
- **`tsconfig.json` with `extends`**: followed only to files inside the analyzed folder. An `extends` to a
  package or to a path outside the folder is ignored, and the file's own settings still apply.
- **`tsconfig.json` or `jsconfig.json` that is not valid JSON-with-comments**: ignored for resolution, and the
  config file is listed in coverage with a `parse_error` flag.
- **Several `tsconfig.json` files**: each TS/JS file uses the nearest one in its folder or a parent folder
  inside the analyzed root.
- **Declaration files** (`*.d.ts`): analyzed like other TS files.
- **Vue, Svelte and Astro components** (`.vue`, `.svelte`, `.astro`): `detected_only` in this slice.
- **Minified or bundled output** (`*.min.js`) and build output folders: skipped with their reason.

## Requirements *(mandatory)*

### Functional Requirements

**Scope and command**

- **FR-001**: The existing `graphora analyze <dir> [--out <file>]` command MUST analyze TypeScript and
  JavaScript files in addition to Python, with no new flags required. All command, safety, limit and
  exit-status requirements from feature 001 (FR-001 … FR-006) apply unchanged.
- **FR-002**: Files with extensions `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, `.cjs` MUST get
  status `analyzed`, with language `typescript` or `javascript`. `.d.ts` files are `typescript`.
- **FR-003**: These folders MUST also be skipped, with reason `excluded_dir`, in addition to the 001 list:
  `.next`, `.nuxt`, `.turbo`, `.svelte-kit`, `coverage`, `out`, `bower_components`.
- **FR-004**: Configuration files (`package.json`, `tsconfig.json`, `jsconfig.json`) MUST be read as data
  only. No script, plugin, loader or build tool named in them is run.

**Extraction**

- **FR-005**: The graph MUST contain one edge per import form and imported name:
  - static `import` declarations (default, named, namespace, side-effect, type-only);
  - `export … from` and `export * from` re-exports (edge type `reexports`);
  - `require("…")` calls;
  - dynamic `import("…")` calls;
  - TypeScript `import x = require("…")`.
- **FR-006**: Each edge MUST record its form: `static`, `dynamic` or `require`, and whether it is type-only.
- **FR-007**: Each TS/JS file node MUST carry a list of its definitions: top-level classes, functions,
  interfaces, type aliases and enums, top-level `const`/`let` bound to an arrow or function expression
  (kind `function`), and methods of top-level classes. Each has a kind, a qualified name and a 1-based line,
  sorted as in feature 001.
- **FR-007a**: Each TS/JS definition MUST record whether it is exported (by `export` on the declaration, by a
  local `export { name }` / `export { name as alias }`, or as `export default`). Each TS/JS file node MUST
  also list its exported names that are not definitions in that file (for example `export { x }` of an
  imported binding), sorted by name. Python definitions do not carry this flag.
- **FR-007b**: The analysis MUST NOT add derived edges by following re-export chains. Only statements written
  in the code become edges; chain-following is left to the graph-query layer.

**Resolution**

- **FR-008**: Relative specifiers (`./`, `../`) MUST resolve against the importing file's folder, in this fixed
  order:
  1. the exact path, if it is a file;
  2. the path with each extension appended, in the order `.ts`, `.tsx`, `.d.ts`, `.mts`, `.cts`, `.js`,
     `.jsx`, `.mjs`, `.cjs`, `.json`;
  3. a specifier ending in `.js`, `.jsx`, `.mjs` or `.cjs` that names a missing file, tried with the matching
     TypeScript extension (`.ts`, `.tsx`, `.mts`, `.cts`);
  4. the path as a folder, with `index` plus each extension from step 2.

  The first match wins. If nothing matches, the edge is `unresolved` with reason `not_found`.
- **FR-009**: Bare specifiers MUST be tried, in order, against:
  1. `paths` aliases of the nearest `tsconfig.json`/`jsconfig.json` (with `extends` followed inside the
     analyzed folder), most specific pattern first, then each listed target in order;
  2. `baseUrl` of that config;
  3. the Node built-in module list;
  4. otherwise, an npm package named by the first segment of the specifier (the first two for `@scope/…`).

  A specifier that matches a `paths` alias but no file is `unresolved` with reason `not_found`. A
  `baseUrl` lookup that finds no file falls through to the next step, as in TypeScript.
- **FR-010**: Before step 3 of FR-009, a bare specifier whose package name matches the `name` of a
  `package.json` inside the analyzed folder (other than the root one) MUST be recorded as `unresolved` with
  reason `workspace_package`. It MUST NOT become an npm package node, and no local file is guessed.
- **FR-011**: The Node built-in module list MUST be a fixed list shipped with the extractor version and MUST
  NOT depend on any Node installation on the machine running the tool.
- **FR-012**: Resolution MUST NOT read `node_modules` or any file outside the analyzed folder.
- **FR-013**: Confidence MUST be `resolved` when the rules above determine the target (a local file, an asset,
  a built-in or an npm package) and `unresolved` otherwise. No edge in this slice is `heuristic`.
- **FR-014**: An unresolved TS/JS edge MUST point to a shared placeholder node. Its reference is the
  repository-relative path that was tried for relative specifiers, and the specifier or expression as written
  otherwise. Placeholders from different languages MUST NOT merge.

**Schema v2**

- **FR-015**: The graph format MUST move to schema version 2. `schema/graph.schema.json` MUST be updated, and
  every output (Python and TS/JS) MUST validate against it and state version 2.
- **FR-016**: Schema v2 MUST allow file nodes with language `python`, `typescript` or `javascript`, and the
  definition kinds `interface`, `type_alias` and `enum` in addition to the v1 kinds.
- **FR-017**: External package nodes MUST record their ecosystem (`python` or `npm`) so that packages with the
  same name in different ecosystems are separate nodes. npm external nodes have category `builtin` or
  `third_party`.
- **FR-018**: Schema v2 MUST add the edge type `reexports`, the edge form (FR-006), the type-only flag, an
  asset node kind for imported non-code files, the unresolved reason `workspace_package`, and the export
  information from FR-007a.
- **FR-019**: Schema v2 MUST keep every v1 rule about provenance: an edge without source, target, type, line,
  column, snapshot, confidence, extractor and snippet hash MUST be rejected, and `unresolved` edges MUST carry a
  reason.
- **FR-020**: The existing Python fixtures' `expected.json` files MUST be updated by hand to schema v2. The only
  allowed differences from v1 are the version number, ecosystem-qualified external and placeholder ids, and the
  new edge form and type-only fields. All Python nodes and edges stay the same.
- **FR-021**: All consumers of the schema present in the repository at merge time MUST be updated in the same
  change (constitution VII).

**Determinism**

- **FR-022**: All feature 001 determinism rules (FR-016, FR-017 there) MUST hold for TS/JS and mixed
  repositories: byte-identical output for the same snapshot and extractor versions, sorted nodes, edges and
  keys, no timestamps or absolute paths.

**Ground truth**

- **FR-023**: At least three new fixture repositories MUST exist in `fixtures/repos/`, each with a
  hand-checked `expected.json`. Together they MUST cover:
  - relative imports with extension and index-file resolution, including `.js` → `.ts`;
  - `tsconfig` `baseUrl`, `paths` and an `extends` chain;
  - ESM static, side-effect, type-only, namespace and default imports;
  - CommonJS `require` and dynamic `import()` with literal and non-literal arguments;
  - Node built-ins with and without `node:` and a scoped npm package;
  - a barrel file with `export *` and named re-exports, and exported and non-exported definitions;
  - a bare import of a local workspace package;
  - an import cycle;
  - a CSS or JSON asset import;
  - a file with a syntax error;
  - a mixed Python + TS repository;
  - a skipped `node_modules` and a build output folder.
- **FR-024**: Automated tests MUST check each fixture's output against its `expected.json`, check that repeated
  runs give identical bytes, and validate the output against schema v2.

### Key Entities

- **File node**: an analyzed Python, TypeScript or JavaScript file with its language and definitions.
- **Definition**: a class, function, method, interface, type alias or enum declared in a file, with qualified
  name, line and (for TS/JS) whether it is exported.
- **External package node**: an imported package not found locally, with its ecosystem (`python`, `npm`) and
  category (`stdlib`/`third_party` for Python, `builtin`/`third_party` for npm).
- **Asset node**: an imported non-code file inside the analyzed folder (stylesheet, JSON, image).
- **Unresolved node**: a placeholder for an import whose target could not be determined, scoped to its
  language.
- **Import / re-export edge**: one statement and imported name, from a file node to a target, with provenance,
  confidence, form and type-only flag.
- **Resolution config**: the `tsconfig.json`/`jsconfig.json` settings (`baseUrl`, `paths`, `extends`) that
  apply to a file.
- **Graph document v2**: schema version 2, snapshot id, extractor versions, nodes, edges and coverage report.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On every TS/JS and mixed fixture, 100% of hand-checked nodes and edges are reproduced, and no
  unexpected node or edge appears.
- **SC-002**: Zero guesses: every import in the fixtures that the documented rules cannot resolve is reported as
  `unresolved`, never as a wrong file or package.
- **SC-003**: All existing Python fixtures still pass after the move to schema v2, with no change to their nodes
  and edges beyond FR-020.
- **SC-004**: 10 consecutive runs on each new fixture, from two different absolute paths, produce
  byte-identical output.
- **SC-005**: A project with about 1,000 TS/JS files is analyzed in under 30 seconds on a typical developer
  laptop.
- **SC-006**: In the barrel fixture, a teammate can find which file defines a name imported through a barrel by
  following edges in the graph alone, in under one minute.
- **SC-007**: 100% of files in each fixture are accounted for in the coverage report, either as an entry or
  under a skipped folder.

## Assumptions

- Feature `002` (repository import from GitHub URL or ZIP) is developed in parallel by another team member. This
  feature depends only on feature 001 and works on a local folder. If 002 also changes the schema, whichever
  merges second rebases onto the other's schema version.
- Resolving workspace packages to their local files is deferred; they are `unresolved` with reason
  `workspace_package` (FR-010).
- `package.json` `exports`/`imports` field resolution for local packages, project references, and custom
  module resolvers (webpack, Vite aliases) are out of scope. Imports that need them stay `unresolved`.
- Mapping npm package names to versions or lockfile entries is out of scope; packages are identified by name.
- Cross-language edges (frontend HTTP call ↔ Python route) are a later heuristic feature; this slice adds none.
- Symbol-level nodes and edges stay deferred, as in feature 001. Definitions are listed on file nodes only.
- No database, HTTP API, UI, MCP server, graph queries or language model are part of this slice.
