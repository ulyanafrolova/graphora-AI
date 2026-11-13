# Research: Python Barrel Following

## R1. Where the bound name is stored

- **Decision**: reuse the edge field `alias` on Python `imports` edges, set only when `as` gives a name different
  from the default one. Schema v7 allows it when the edge comes from the Python adapter.
- **Rationale**: `alias` already exists, is part of the edge sort key and the edge id, and means the same
  thing for TS/JS re-exports (the name the binding is known under). No new field for consumers to learn.
- **Alternatives**: Python `exports` lists or `reexports` edges as in TS/JS (issue #16 first idea): needs
  deciding what counts as an export without `__all__`, and duplicates information the import edges already
  carry. A query-only approach without `alias`: cannot tell `from .x import f as g` from `from .x import f`,
  so links would have to be `heuristic`.

## R2. What `alias` holds for each import form

| Code | symbol | alias |
|---|---|---|
| `from .x import f` | `f` | none |
| `from .x import f as g` | `f` | `g` |
| `from .x import f as f` | `f` | none (same name) |
| `import a.b` | none | none |
| `import a.b as c` | none | `c` |
| `from .x import *` | `*` | none (no `as` possible) |
| dynamic imports | none | none |

`from .x import f, f as g` gives two edges (different `alias`), as the edge list is deduplicated on the full
edge. The schema allows `alias` only on Python `imports` edges, recognised by `extractor` starting with
`python-adapter@`.

## R3. How a Python file passes a name on (query side)

- **Decision**: `_trace` gets a Python branch. For Python file `F` and name `n`:
  1. `F` defines `n` as a top-level class or function → stop at `F`.
  2. `F` has a resolved or heuristic static `imports` edge to a `file:` target whose bound name
     (`alias or symbol`) is `n`, with symbol not `*` → follow into the target with the edge's `symbol`
     (for `import a.b as c`, symbol is none: stop at the target, the name is the whole module). If the target
     neither defines nor passes on the name, stop at the target: a resolved import proves the name comes from
     there (module-level constants are not in `definitions`).
  3. Otherwise → not traced; the importer stays on `F`.
  Edges are tried in sort order; a file already on the path is skipped.
- **Rationale**: this is Python's own rule: after `from x import n [as m]`, the module has attribute `m`.
  Restricting to `__init__.py` would be an arbitrary cut; ordinary modules work the same way.
- **Submodules**: `from . import server` resolves to `server.py` with symbol `server`; tracing into
  `server.py` finds no definition or import named `server` and stops at `server.py`, which is right.

## R4. Symbol filter

- **Decision**: `dependents --symbol N --follow-barrels` keeps barrel links whose import edge has symbol `N`,
  as for TS/JS today. An importer of a renamed name (`from pkg import make_server`) is not kept for
  `--symbol create_server`.
- **Rationale**: FR-010 forbids changing TS/JS answers, and TS/JS behaves this way. Changing both together is a
  separate decision.

## R5. Confidence

Derived link confidence = weakest of the import edge and every edge in the chain, as `_barrel_links` already
computes. Unresolved edges are dropped before tracing.

## R6. Version and compatibility

- Schema 6 → 7; `python-adapter` 0.3.0 → 0.4.0. Graph files of version 6 are rejected by the loader with the
  existing message; stored analyses are made again because the extractor versions differ.
- `tests/golden/v1/*.json` are frozen v1 answers: the v1 projection drops `alias` like the other later fields.

## Implementation notes

- SC-001 on this repository's backend (2026-11-13): `dependents src/graphora/mcp/server.py --symbol create_server`
  gives 1 file without barrel following and 8 with it: `mcp/__init__.py` plus 7 importers through
  `graphora.mcp` (`cli/__init__.py` and 6 test files; `test_api_jobs.py` came with 010).
- SC-005: on 5,000 modules in 50 re-exporting packages, `dependents` with barrels takes about 0.13 s and
  `impact` about 0.10 s (`tests/integration/test_query_performance.py`).
- The submodule case (`from pkg import server`) needs no tracing: the resolver already points it at
  `pkg/server.py` (fixture `run.py`).
