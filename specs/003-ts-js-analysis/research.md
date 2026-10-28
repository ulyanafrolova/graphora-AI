# Research: TypeScript/JavaScript Analysis (Graph Schema v2)

Every decision below resolves an open point from the plan's Technical Context. Decisions from
[001 research](../001-python-graph-cli/research.md) (R1–R10) still apply unless a section here replaces
them. Versions were checked with `uv pip install --dry-run` on 2026-10-28, and the grammars were parsed
against a probe file covering every import form in the spec.

## R1. Parsers

- **Decision**:
  - Add `tree-sitter-typescript==0.23.2` and `tree-sitter-javascript==0.25.0`, pinned exactly, next to the
    existing `tree-sitter==0.26.0`.
  - Pick the grammar by extension:

    | Extensions | Grammar | Language label |
    |---|---|---|
    | `.ts`, `.mts`, `.cts`, `.d.ts` | `typescript` | `typescript` |
    | `.tsx` | `tsx` | `typescript` |
    | `.js`, `.jsx`, `.mjs`, `.cjs` | `javascript` (includes JSX) | `javascript` |

  - One adapter, `js-adapter@0.1.0`, serves all three grammars. Its version changes whenever a grammar pin
    or the extraction logic changes.
- **Rationale**:
  - Tree-sitter is the constitution's parser, it tolerates syntax errors, and it never runs code.
  - The probe showed that the `typescript` grammar rejects JSX and `tsx` accepts it, which matches how
    `tsc` treats `<T>x` casts. Choosing by extension is therefore required for correct parse-error flags.
  - The JavaScript grammar parses JSX in `.js` files, which is common in React projects.
  - One adapter keeps one extraction logic for both languages. They share the module system, so they also
    share resolution.
- **Alternatives considered**:
  - Parsing everything with `tsx`: it misparses TS angle-bracket casts in `.ts` files.
  - Running `tsc` or `esbuild` to resolve modules: needs Node, and it would run a toolchain chosen by the
    repository (Principle I).
  - Babel or SWC through Node: an extra runtime, and not Tree-sitter.

## R2. What the adapter extracts

- **Decision**: one `ImportRecord` per statement or call, with one entry per imported name:

  | Source | Edge type | Form | Symbol | Alias |
  |---|---|---|---|---|
  | `import x from "m"` | `imports` | `static` | `default` | — |
  | `import { a, b as c } from "m"` | `imports` | `static` | `a`, `b` | — |
  | `import * as ns from "m"` | `imports` | `static` | `*` | — |
  | `import "m"` | `imports` | `static` | `null` | — |
  | `import type { T } from "m"`, `import { type T } from "m"` | `imports` | `static`, type-only | `T` | — |
  | `import x = require("m")` (TS) | `imports` | `require` | `null` | — |
  | `require("m")`, anywhere | `imports` | `require` | `null` | — |
  | `import("m")`, anywhere | `imports` | `dynamic` | `null` | — |
  | `export * from "m"` | `reexports` | `static` | `*` | — |
  | `export * as ns from "m"` | `reexports` | `static` | `*` | `ns` |
  | `export { a, b as c } from "m"` | `reexports` | `static` | `a`, `b` | — / `c` |
  | `export type { T } from "m"` | `reexports` | `static`, type-only | `T` | — |

  - `require` counts only when the callee is the plain identifier `require` and there is exactly one
    argument. Shadowing is not tracked (spec edge case).
  - A specifier is a literal if it is a string, or a template string without substitutions. Anything else
    (`require(name)`, `import(\`./p/${n}\`)`, `"./a" + b`) gives an unresolved edge with reason `dynamic`.
    The reference is the call text as written.
  - **Not extracted in this slice**: `/// <reference path>` directives, `declare module "x"` blocks,
    `import x = A.B` namespace aliases, `require.resolve`, `module.exports` / `exports.x` (CommonJS
    exports) and `export =`. They are recorded in the Assumptions of the plan.
- **Rationale**:
  - These forms cover the spec (FR-005, FR-006).
  - Symbols mirror Python: the symbol is the name *in the target module*, so chain-following can match a
    re-export to a definition.
  - `alias` exists only on re-exports, because only there does the new name matter for following a chain
    (`export { Log as Logger }`). Import aliases only rename a local binding.
- **Alternatives considered**:
  - Adding `alias` to every edge, Python included: it changes Python output beyond what FR-020 allows and
    has no consumer yet.
  - Tracking CommonJS `module.exports`: needs data-flow analysis to be honest, so it is deferred.

## R3. Snippet hash, edge id and order

- **Decision**:
  - The snippet hash is unchanged from 001 R4: whitespace-collapsed text of the whole statement, or of the
    call for `require` and `import()`.
  - The edge id becomes `e:` + 16 hex of SHA-256 over
    `source|line|column|target|symbol|alias|type`, with empty strings for null values.
  - Edges sort by `(source, line, column, target, symbol ?? "", alias ?? "", type)`.
- **Rationale**: `export { a as b, a as c } from "./x"` gives two edges with the same position, target and
  symbol, so the alias has to be in the id. Including `type` costs nothing and keeps ids unique if a later
  type shares a position. Python ids change anyway, because their targets get ecosystem prefixes (R7).
- **Alternatives considered**: keeping the v1 formula and adding the alias only when present. The formula
  would then depend on optional fields, which is harder to test.

## R4. Reading `tsconfig.json` and `jsconfig.json`

- **Decision**:
  - Parse with a small in-house JSONC reader: strip `//` and `/* */` comments outside strings and drop
    trailing commas, then `json.loads`. If the result is not a JSON object, the config counts as absent and
    its coverage entry gets the `parse_error` flag. Files fall back to the next valid ancestor config, and
    a broken `extends` entry is skipped.
  - Read only `extends`, `compilerOptions.baseUrl` and `compilerOptions.paths`. `include`, `exclude`,
    `files`, `references` and `moduleResolution` are ignored.
  - **Nearest config.** For each TS/JS file, take the closest ancestor folder (inside the root) that has
    `tsconfig.json`, or else `jsconfig.json`. If both are in the same folder, `tsconfig.json` wins.
  - **`extends`.** A string or an array (TS 5.0). Each entry must be a relative path. It is tried as
    written, then with `.json` appended. It must stay inside the root and must not be a skipped path.
    Package names, absolute paths and paths that leave the root are ignored. Array entries apply in order,
    and later entries override earlier ones, before the child's own options. Cycles stop at the first
    repeat.
  - **Where relative paths are anchored.** `baseUrl` is relative to the config that defines it. `paths`
    targets are relative to the effective `baseUrl`, or to the folder of the config that defines `paths`
    when no `baseUrl` is set.
- **Rationale**:
  - The stdlib `json` module rejects comments, which almost every `tsconfig.json` has.
  - A dependency for 40 lines of code is not worth it, and an in-house reader is deterministic.
  - These anchoring rules are TypeScript's documented behaviour since 4.1.
- **Alternatives considered**:
  - The `json5` or `pyjson5` packages: an extra dependency, and they accept more syntax than `tsc` does.
  - Honouring `include` and `exclude` to pick the config: needs glob semantics, while "nearest folder"
    matches what editors do for most projects.

## R5. Specifier resolution

- **Decision**: the full rule table is in [data-model.md § Resolution](data-model.md). In short:
  - **Relative** (`./`, `../`) follows the spec's FR-008 order: exact file, extensions, `.js` → `.ts`
    substitution, then folder index.
  - **Bare** follows FR-009 and FR-010: `paths`, then `baseUrl`, then workspace packages, then Node
    built-ins, then npm.
  - The candidate set is every walked, non-skipped file. A match on an `analyzed` file gives a `file:`
    target. A match on any other included file gives an `asset:` target.
  - **Always `unresolved` with reason `not_found`**, with the specifier as written as the reference:
    - absolute paths (`/x`);
    - URLs (`https:`, `data:`, `file:`);
    - `#` subpath imports;
    - `node:` names that are not built-ins;
    - relative paths that leave the root.
  - **Package names.** The top-level package name is the first segment of the specifier, or the first two
    for `@scope/name`. Built-ins use the top segment too, so `fs/promises` becomes `fs`.
- **Rationale**:
  - These are the module rules of TypeScript and Node, minus everything that needs `node_modules`, a
    bundler or `package.json` `exports`/`imports`. Those cases stay unresolved instead of guessed
    (Principle IV).
  - Built-ins collapse to the top name, mirroring Python's top-level external nodes.
  - Workspace names are checked before built-ins and npm, so that a local package is never labelled
    external.
- **Alternatives considered**:
  - Built-ins before `paths`: TypeScript tries `paths` first, so a `paths` entry named `fs` must win.
  - A new reason `unsupported` for URLs and `#` imports: the spec defines only `workspace_package` as a
    new reason, and `not_found` is accurate (no file was found by the rules). This can be split later.

## R6. Node built-in module list

- **Decision**:
  - Commit `backend/src/graphora/resolve/data/node_builtins.txt` as the union of `module.builtinModules`
    for Node 20, 22 and 24, plus the prefix-only modules (`node:test`, `node:sqlite`, `node:sea`,
    `node:test/reporters`). Prefix-only names are marked so that bare `test` stays an npm package.
  - The list is versioned `node-builtins@24.0.0` in `extractors`.
  - `backend/scripts/gen_node_builtins.py` documents how the list was produced. It needs a local Node and
    is never run by tests or by `analyze`.
- **Rationale**: FR-011 requires that the list does not depend on the machine. Using the union classifies
  older projects correctly.
- **Alternatives considered**: calling `node` at runtime: not deterministic, and it adds a runtime
  dependency.

## R7. Schema v2

- **Decision**: [contracts/graph.schema.json](contracts/graph.schema.json) replaces v1 in
  `schema/graph.schema.json`. The changes:

  | Area | v1 | v2 |
  |---|---|---|
  | `schema_version` | `1` | `2` |
  | File `language` | `python` | `python` \| `typescript` \| `javascript` |
  | Definition kinds | `class`, `function`, `method` | + `interface`, `type_alias`, `enum` |
  | Definition `exported_as` | — | Required on TS/JS, forbidden on Python |
  | File `exports` | — | Required on TS/JS, forbidden on Python |
  | External id | `ext:<name>` | `ext:<ecosystem>:<name>`, plus field `ecosystem` |
  | External `category` | `stdlib` \| `third_party` | Python: `stdlib` \| `third_party`; npm: `builtin` \| `third_party` |
  | Unresolved id | `unresolved:<ref>` | `unresolved:<ecosystem>:<ref>`, plus field `ecosystem` |
  | Asset node | — | `asset:<path>`, fields `path` |
  | Edge `type` | `imports` | `imports` \| `reexports` |
  | Edge `form`, `type_only` | — | Required on every edge |
  | Edge `alias` | — | Optional, only on `reexports` |
  | Reasons | 4 | + `workspace_package` |

  - The ecosystem values are `python` and `npm`. `npm` covers TS and JS, because both share one module
    namespace.
  - Python edges get `form` (`static`, or `dynamic` for `importlib` / `__import__`) and
    `type_only: false`.
  - `python-adapter` and `python-resolver` become `0.2.0`, because their output gains fields and ids
    change.
- **Rationale**:
  - These are the minimal changes for FR-015 … FR-019.
  - Export information is a list of names (`exported_as`) instead of a boolean, because one definition can
    be exported under several names (`export default`, `export { f as g }`), and chain-following needs the
    names (spec FR-007a).
  - Names that are exported but have no definition (`export const x = 1`, `export { importedThing }`,
    `export default expr`) go into the file's `exports` list, so every exported name appears exactly once.
- **Alternatives considered**:
  - A boolean `exported`: it loses aliases and `default`, and it cannot express exported non-definitions.
  - Separate schemas per language: the frontend wants one contract (constitution VII).

## R8. Code structure

- **Decision**:
  - New modules:
    - `adapters/js/` for extraction;
    - `resolve/js.py` for specifier resolution;
    - `resolve/tsconfig.py` for config loading and JSONC.
  - `graph/build.py` dispatches by coverage language, and both adapters return the same `FileFacts` shape.
  - The model gains `AssetNode` and new fields, and `serialize.py` writes schema v2.
  - The Python resolver keeps its rules. Only the node ids it returns change, to the ecosystem form.
- **Rationale**: this mirrors the 001 layout (one adapter folder and one resolver per language), so a third
  language later is an addition, not a rewrite.
- **Alternatives considered**: a plugin registry for adapters. That is premature with two languages.

## R9. Fixtures and golden projection

- **Decision**:
  - Four new fixtures, listed in the plan.
  - The projection in `tests/conftest.py` gains:
    - for nodes: `ecosystem`, the asset `path`, and `exported_as` / `exports` on TS/JS file nodes;
    - for edges: `type` and `form` always, and `type_only` and `alias` only when they are `true` or set.
  - The three Python `expected.json` files are edited by hand. They get the new ids and ecosystems, and
    `type: "imports"` plus `form` on every edge. Nothing else changes (FR-020).
  - A test asserts that the Python fixtures' edge sets, with ids mapped back to v1 form, equal the v1
    expected edge sets. The v1 files are copied once from commit `732e98c` into
    `backend/tests/golden/v1/` as frozen test data, so the test needs no git access and survives a squash
    merge of 001. This proves SC-003.
- **Rationale**: projecting only non-default flags keeps hand-written files short. The v1-equivalence
  check makes the "nothing else changed" claim mechanical rather than a review promise.
- **Alternatives considered**: keeping the Python fixtures in a v1 projection and translating in the test.
  That hides the schema change from reviewers of `expected.json`.

## R10. Coordination with feature 002

- **Decision**:
  - 003 changes `schema/graph.schema.json`, `graph/model.py`, `graph/serialize.py`, `graph/build.py` and
    `detect/languages.py`, and adds skip names to `ingest/walk.py`.
  - If 002 merges first and touches the same files, 003 rebases. If 002 adds a schema field, 003 folds it
    into v2. If 003 merges first, 002 rebases onto v2.
- **Rationale**: constitution VII allows one schema version change per change set, with all consumers
  updated. Two parallel bumps to "v2" must not both land.
- **Alternatives considered**: a separate v3 for whichever merges second. That is two bumps in a week with
  no external consumers, which is noise.
