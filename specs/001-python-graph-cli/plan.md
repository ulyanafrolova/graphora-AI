# Implementation Plan: Python Import Graph CLI

**Branch**: `001-python-graph-cli` | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-python-graph-cli/spec.md`

## Summary

This slice adds `graphora analyze <dir>`, which reads a local folder as text only and writes one
deterministic JSON graph document. The document contains:

- a file node for every Python file, with its class, function and method definitions;
- an external node for every imported stdlib or third-party package;
- an `unresolved:` placeholder node for every import that cannot be resolved;
- one edge per imported name, with full provenance;
- a coverage report for every file in the folder.

How it works:

- **Parsing.** Tree-sitter parses the Python files, and a rule-based resolver
  ([data-model.md § Resolution](data-model.md)) maps each import to a target, an external package or
  `unresolved`. It never guesses.
- **Snapshot id.** It is computed from git blob ids, read with dulwich, without ever running `git`. For
  folders that are not git, it falls back to `content:<hash>`.
- **Ground truth.** Three fixture repositories with hand-written `expected.json` files are the ground
  truth for golden tests, alongside determinism tests and schema tests.

## Technical Context

**Language/Version**: Python ≥ 3.12, developed on 3.14

**Primary Dependencies**: `tree-sitter==0.26.0`, `tree-sitter-python==0.25.0` and `dulwich==1.2.19`. Dev
only: `pytest==9.1.1` and `jsonschema==4.26.0`. Research: [R1–R9](research.md)

**Storage**: None. The output is one JSON file

**Testing**: pytest, with golden, contract (schema), integration (snapshot, safety, CLI) and unit tests

**Target Platform**: macOS and Linux developer machines and CI

**Project Type**: CLI, as the first module set of the `backend` package

**Performance Goals**: about 1,000 Python files in under 30 seconds on a laptop (SC-005)

**Constraints**:

- byte-identical output;
- no execution of analyzed content and no `git` subprocess;
- default limits of 5,000 files, 50 MB and 300 s;
- nothing written inside the analyzed folder.

**Scale/Scope**: fixtures have 10–25 files each, and real targets have up to 5,000 files

No open questions remain.

## Constitution Check

*GATE: checked before Phase 0, and re-checked after Phase 1.*

| Principle | How this plan complies | Status |
|---|---|---|
| I. Never execute analyzed code | Files are read as bytes and parsed by Tree-sitter. Nothing is imported or built. Git is read by dulwich with no subprocess, so filters, hooks and fsmonitor never run (R3). Symlinks are never followed, and a symlinked `.git` or a repository with alternates or `commondir` falls back to `content:<hash>`. File and byte limits are enforced before parsing, and the 300 s time limit is checked during the run. A safety integration test checks all of this | ✅ |
| II. Deterministic output | Every list is sorted explicitly, keys are sorted, and output is LF with a trailing newline. There are no timestamps or absolute paths. The stdlib list is fixed (R5). Hashes depend only on paths and bytes (R4). Tests run 10 times and on a copied path | ✅ |
| III. Provenance on every edge | The schema requires source, target, type, line, column, snapshot, confidence, extractor@version and snippet_hash on every edge, and the contract test rejects edges without them. The `content:<hash>` id form is added by a PATCH amendment in this PR (FR-016a). **Node provenance:** a file node is located by its `path` plus the document `snapshot`, and a definition by its `line` plus its file's `path`. External and unresolved nodes exist only as targets of edges that carry full provenance. No node is emitted without at least one of these anchors | ✅ (after amendment) |
| IV. Honest confidence | Only the three levels exist. Unresolved edges carry a `reason`. The resolver has no fallback guessing. `.py` and `.pyi` are `analyzed`, other languages are `detected_only` | ✅ |
| V. Facts by code | There is no LLM in this slice | ✅ (n/a) |
| VI. Analyzed content is data | No model reads content in this slice. The snippet text is not copied into the output, only its hash | ✅ (n/a) |
| VII. One graph query layer | The graph model and serializer live in `graphora/graph/`. `schema/graph.schema.json` v1 is created here as the single contract | ✅ |
| VIII. Golden tests | Three fixtures with hand-checked `expected.json`, plus determinism tests | ✅ |
| Tech constraints | `uv`, Tree-sitter and Python as required. NetworkX, FastAPI, PostgreSQL and LangGraph are not needed yet, and adding them would be scaffolding ahead of a spec (R9) | ✅ |
| Workflow | One branch and one PR. Specs cover only this slice | ✅ |

**Re-check after Phase 1:** the design adds no violations. The schema check in
[research](research.md) showed that the contract enforces Principle III: an edge without a hash, an
unresolved edge without a reason, and a resolved edge pointing to a placeholder are all rejected.

## Project Structure

### Documentation (this feature)

```text
specs/001-python-graph-cli/
├── spec.md
├── plan.md                # this file
├── research.md            # R1–R10
├── data-model.md          # entities, resolution rules
├── quickstart.md          # validation guide
├── contracts/
│   ├── graph.schema.json  # becomes schema/graph.schema.json
│   └── cli.md
├── checklists/requirements.md
└── tasks.md               # /speckit-tasks
```

### Source Code (repository root)

```text
schema/
└── graph.schema.json                 # v1, copied from contracts/

backend/
├── pyproject.toml                    # uv project "graphora", console script graphora = graphora.cli:main
├── scripts/gen_stdlib_list.py        # regenerates resolve/data/stdlib_modules.txt
├── src/graphora/
│   ├── __init__.py
│   ├── cli/__init__.py               # argparse, exit codes, atomic write
│   ├── ingest/
│   │   ├── walk.py                   # walk the folder, skip rules, symlinks, limits
│   │   └── snapshot.py               # dulwich blob-map comparison, content hash
│   ├── detect/languages.py           # extension and marker tables, coverage status
│   ├── adapters/python/
│   │   ├── __init__.py               # version string python-adapter@0.1.0
│   │   └── extract.py                # Tree-sitter: imports, dynamic imports, definitions, parse errors
│   ├── resolve/
│   │   ├── python.py                 # module index, namespace packages, resolution table
│   │   └── data/stdlib_modules.txt
│   └── graph/
│       ├── build.py                  # walk → snapshot → extract → resolve → GraphDocument
│       ├── model.py                  # Node, Edge, Coverage, GraphDocument dataclasses
│       └── serialize.py              # sorting, ids, canonical JSON
└── tests/
    ├── golden/test_fixtures.py       # projection == expected.json, determinism
    ├── contract/test_schema.py       # outputs valid; invalid samples rejected
    ├── integration/
    │   ├── test_cli.py               # exit codes, --out rules, no partial output
    │   ├── test_snapshot.py          # clean, dirty and content forms in temp git repositories
    │   └── test_safety.py            # import marker and git filter marker never appear
    └── unit/                         # extract, resolve, hashes, walk

fixtures/repos/
├── py-flat/{repo/, expected.json}        # absolute and relative imports, from-import of submodule vs
│                                         #   attribute, cycle a↔b, stdlib + third-party, relative
│                                         #   beyond top, missing local, import *, classes and methods
├── py-src-layout/{repo/, expected.json}  # src/app package, tests/ importing app, namespace package,
│                                         #   pyproject.toml marker, .pyi stub next to a .py file
└── py-dynamic/{repo/, expected.json}     # import_module(var), import_module("lit"), __import__,
                                          #   aliased importlib, imports in a function / TYPE_CHECKING /
                                          #   try, syntax-error file, non-UTF-8 .py, .ts and .md files,
                                          #   .venv/, __pycache__/, symlink, *.min.js, import-time marker

.gitattributes                            # fixtures/repos/** -text
.specify/memory/constitution.md           # PATCH 1.0.1: content:<hash> snapshot form
```

**Structure Decision**:

- This is the backend half of the target layout in CLAUDE.md. Only the module folders this slice needs are
  created.
- `api/`, `mcp/`, `agents/`, `store/` and `verify/` appear in later slices.
- The query functions in `graph/` arrive together with NetworkX in the graph-queries slice.

## Complexity Tracking

No constitution violations to justify. The `content:<hash>` snapshot form is handled by a PATCH
amendment, not by a deviation.
