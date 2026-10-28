# Implementation Plan: TypeScript/JavaScript Analysis (Graph Schema v2)

**Branch**: `003-ts-js-analysis` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-ts-js-analysis/spec.md`

## Summary

This slice makes `graphora analyze` fully analyze TypeScript and JavaScript next to Python. It also moves
the graph format to schema v2 for every language.

What the output gains:

- a file node for every TS/JS file, with its definitions and export names;
- `imports` and `reexports` edges for every ESM import, re-export, `require` and `import()`, each with
  full provenance, a form and a type-only flag;
- external nodes qualified by ecosystem (`ext:npm:react`, `ext:python:yaml`), Node built-ins, asset nodes
  for imported CSS/JSON/images, and unresolved placeholders scoped by ecosystem.

How it works:

- **Parsing.** Tree-sitter parses TS, TSX and JS, choosing the grammar by extension (R1).
- **Resolution.** A rule-based resolver ([data-model.md § Resolution](data-model.md)) handles relative
  specifiers, extension and index lookup, `.js` → `.ts`, `tsconfig`/`jsconfig` `baseUrl`, `paths` and
  `extends` (read as JSONC data, R4), Node built-ins from a shipped list (R6), npm packages, and local
  workspace packages, which are marked `unresolved: workspace_package`.
- **No guessing.** It never reads `node_modules`, never runs Node and never follows re-export chains
  (FR-007b).
- **Python.** It keeps its resolution rules. Only the serialization moves to v2, and its fixtures are
  updated by hand.

## Technical Context

**Language/Version**: Python ≥ 3.12, developed on 3.14 (unchanged)

**Primary Dependencies**: adds `tree-sitter-typescript==0.23.2` and `tree-sitter-javascript==0.25.0` to the
existing `tree-sitter==0.26.0`, `tree-sitter-python==0.25.0` and `dulwich==1.2.19`. No new dev
dependencies. Research: [R1–R10](research.md)

**Storage**: None. The output is one JSON file

**Testing**: pytest, with golden (4 new fixtures plus 3 migrated), contract (schema v2 accept/reject
samples), unit (extract, resolve, tsconfig/JSONC, serialize) and integration (safety, CLI, performance)
tests

**Target Platform**: macOS and Linux developer machines and CI. No Node.js required

**Project Type**: CLI, inside the `backend` package

**Performance Goals**: about 1,000 TS/JS files in under 30 seconds on a laptop (SC-005). The resolver
caches `try()` results per path and the effective config per folder

**Constraints**:

- byte-identical output;
- no execution of analyzed content, no Node or `git` subprocess;
- no reads outside `<dir>` or inside skipped folders;
- 001 limits unchanged.

**Scale/Scope**: fixtures have 10–30 files each, and real targets have up to 5,000 files

No open questions remain. During planning the spec's FR-009 was corrected: a `baseUrl` miss falls through
to the next step, as in TypeScript. Otherwise every npm import in a project with `baseUrl` would have
become `unresolved`.

## Constitution Check

*GATE: checked before Phase 0, and re-checked after Phase 1.*

| Principle | How this plan complies | Status |
|---|---|---|
| I. Never execute analyzed code | TS/JS files are parsed by Tree-sitter only. `tsconfig.json`, `jsconfig.json` and `package.json` are read as data by an in-house JSONC reader. Only `extends`, `baseUrl`, `paths` and `name` are used. No Node, `tsc`, bundler or package script is ever run. `extends` and every resolution candidate are limited to walked files inside `<dir>`, so symlinks, skipped folders (`node_modules`) and paths outside the root are never read. The safety test gains an `extends: "../../outside.json"` case and a marker file in `node_modules` | ✅ |
| II. Deterministic output | Fixed extension order, fixed `paths` specificity order, fixed built-in list (R6). Edges sort by `(source, line, column, target, symbol, alias, type)`, and the id includes `alias` and `type` (R3). `exported_as` and `exports` are sorted. The determinism tests cover the new fixtures | ✅ |
| III. Provenance on every edge | Every TS/JS edge carries the same required fields as v1 plus `form` and `type_only`. The schema rejects an edge missing any of them. Asset nodes are anchored by `path` plus the snapshot. Export entries carry a `line` | ✅ |
| IV. Honest confidence | No `heuristic` edges. Dynamic specifiers, missing files, `paths` misses, URLs, `#` imports and workspace packages are `unresolved` with a reason. Re-export chains are not followed (FR-007b). Vue, Svelte and Astro stay `detected_only` | ✅ |
| V. Facts by code | There is no LLM in this slice | ✅ (n/a) |
| VI. Analyzed content is data | No model reads content. Snippets are hashed, not copied | ✅ (n/a) |
| VII. One graph query layer | Model and serializer stay in `graphora/graph/`. The schema version is bumped to 2, and every consumer in the repository (serializer, tests, all 7 fixtures) is updated in this PR (FR-021). Coordination with 002 is in R10 | ✅ |
| VIII. Golden tests | Four new hand-checked fixtures, three migrated ones, and a v1-equivalence test for Python (R9) | ✅ |
| Tech constraints | `uv`, Tree-sitter and Python as required. TS/JS is the second MVP language named by the constitution | ✅ |
| Workflow | One branch and one PR, and the spec covers only this slice. The branch starts from `001-python-graph-cli` and rebases onto `main` after 001 merges | ✅ |

**Re-check after Phase 1:** the design adds no violations. The draft
[contracts/graph.schema.json](contracts/graph.schema.json) was checked with 17 invalid samples, and all of
them are rejected. The samples include:

- an edge without `form`, `type_only` or `snippet_hash`;
- an `alias` on an `imports` edge;
- a Python definition with `exported_as`;
- an npm package with category `stdlib`;
- a v1-style `ext:react` id;
- a resolved edge pointing to a placeholder;
- an unresolved edge without a reason.

## Project Structure

### Documentation (this feature)

```text
specs/003-ts-js-analysis/
├── spec.md
├── plan.md                # this file
├── research.md            # R1–R10
├── data-model.md          # v2 changes, TS/JS definitions, exports, resolution table
├── quickstart.md          # validation guide
├── contracts/
│   ├── graph.schema.json  # v2, becomes schema/graph.schema.json
│   └── cli.md             # changes to the 001 CLI contract
├── checklists/requirements.md
└── tasks.md               # /speckit-tasks
```

### Source Code (repository root)

```text
schema/
└── graph.schema.json                 # v1 → v2, copied from contracts/

backend/
├── pyproject.toml                    # + tree-sitter-typescript, tree-sitter-javascript
├── scripts/gen_node_builtins.py      # documents and regenerates node_builtins.txt (needs local Node; never run by tests)
├── src/graphora/
│   ├── adapters/
│   │   ├── python/
│   │   │   ├── __init__.py           # python-adapter@0.2.0
│   │   │   └── extract.py            # + form on records; otherwise unchanged
│   │   └── js/
│   │       ├── __init__.py           # js-adapter@0.1.0, grammar per extension
│   │       └── extract.py            # imports, re-exports, require, import(), definitions, exports, parse errors
│   ├── resolve/
│   │   ├── python.py                 # returns ext:python: / unresolved:python: ids
│   │   ├── js.py                     # try(), relative, paths, baseUrl, workspace, built-ins, npm
│   │   ├── tsconfig.py               # JSONC reader, nearest config, extends chain, effective baseUrl/paths
│   │   └── data/
│   │       ├── stdlib_modules.txt
│   │       └── node_builtins.txt     # node-builtins@24.0.0
│   ├── detect/languages.py           # TS/JS analyzed; .vue/.svelte/.astro detected_only; jsconfig.json marker
│   ├── ingest/walk.py                # + .next, .nuxt, .turbo, .svelte-kit, coverage, out, bower_components
│   └── graph/
│       ├── build.py                  # dispatch by language; collect configs and workspace names
│       ├── model.py                  # + AssetNode, ecosystem, form, type_only, alias, exported_as, exports
│       └── serialize.py              # SCHEMA_VERSION = 2, new id and sort keys
└── tests/
    ├── conftest.py                   # projection gains type, form, flags, alias, ecosystem, exports
    ├── golden/test_fixtures.py       # + v1-equivalence test for Python fixtures; extractor check per language
    ├── contract/test_schema.py       # v2 accept/reject samples
    ├── integration/
    │   ├── test_safety.py            # + outside-root extends, node_modules marker, no subprocess
    │   └── test_performance.py       # + ~1,000 generated TS files
    └── unit/
        ├── test_js_extract.py
        ├── test_js_resolve.py
        └── test_tsconfig.py

fixtures/repos/
├── py-flat/, py-src-layout/, py-dynamic/   # expected.json migrated to v2 by hand
├── ts-app/{repo/, expected.json}           # tsconfig extends + baseUrl + paths (exact and *), relative,
│                                           #   index, .js→.ts, .d.ts, default/named/namespace/side-effect,
│                                           #   import type and inline type, import = require, node:fs/fs,
│                                           #   fs/promises, scoped deep import, CSS and JSON assets, missing
│                                           #   asset, missing relative, missing alias, cycle, TSX with JSX
│                                           #   and decorators, syntax-error file, .vue file, node_modules/,
│                                           #   dist/, .next/
├── js-commonjs/{repo/, expected.json}      # require literal/non-literal, template literal with and without
│                                           #   substitutions, import() in a function, .mjs/.cjs, jsconfig.json
│                                           #   paths, node:test vs bare test, # import, URL import, ../ above
│                                           #   root, broken jsconfig, *.min.js
├── ts-monorepo/{repo/, expected.json}      # packages/ui barrel: export *, export {a as b} from,
│                                           #   export * as ns, export type from; exported and private
│                                           #   definitions, export default expr, export const value, local
│                                           #   export {f as g}, import-then-export; overloads;
│                                           #   packages/app imports @acme/ui (workspace_package) and the
│                                           #   barrel by relative path; one tsconfig per package
└── mixed-fullstack/{repo/, expected.json}  # backend/*.py + frontend/src/*.tsx; yaml imported from both;
                                            #   pyproject.toml and package.json markers
```

**Structure Decision**:

- This extends the 001 layout with a second adapter folder and resolver, as research R8 explains.
- No new top-level folders. `api/`, `mcp/`, `agents/`, `store/` and `verify/` still belong to later slices.
- Nothing is added to `frontend/`, which does not exist yet. The schema stays the frontend's contract.

## Complexity Tracking

No constitution violations to justify.
