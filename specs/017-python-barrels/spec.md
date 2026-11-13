# Feature Specification: Python Barrel Following

**Feature Branch**: `017-python-barrels`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: issue #16 — barrel following for Python. `dependents --follow-barrels` and
`impact --follow-barrels` (CLI and MCP) see through Python package re-exports (`__init__.py`), as they already
do for TS/JS `index.ts`. The analyzer records the name bound by `as` on Python imports, so the query layer can
tell exactly which names a Python file makes importable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See who really uses a function behind `__init__.py` (Priority: P1)

A developer (or a coding agent over MCP) asks who uses `create_server` in `graphora/mcp/server.py`. The
package exposes it in `graphora/mcp/__init__.py` with `from graphora.mcp.server import create_server`, and the
rest of the code writes `from graphora.mcp import create_server`. Today the dependents answer lists only
`mcp/__init__.py`, so an agent concludes that almost nobody uses the function. With barrel following on, the
answer lists every file that imports `create_server` through the package, each with both lines as evidence:
its own import and the import in `__init__.py`.

**Why this priority**: Re-exporting a public API from `__init__.py` is the common Python layout (Graphora
itself, FastAPI, Django). Without it, direct dependents of Python modules collapse into `__init__.py`, and
agents, the main MCP users, take the short list at face value. TS/JS already gets this from feature 004.

**Independent Test**: Run dependents with barrel following on the new `py-barrels` fixture and compare with
hand-written answers.

**Acceptance Scenarios**:

1. **Given** `pkg/__init__.py` has `from .service import AuthService` on line 1 and `app.py` has
   `from pkg import AuthService` on line 3, **When** the dependents of `pkg/service.py` are asked with barrel
   following on, **Then** `app.py` is listed, with the edge at `app.py:3` and the edge at `pkg/__init__.py:1`
   as evidence, and `pkg/__init__.py` is still listed as a direct dependent.
2. **Given** the same files, **When** barrel following is off, **Then** the answer is exactly what it is today:
   `pkg/__init__.py` only.
3. **Given** a symbol filter `AuthService`, **When** dependents of `pkg/service.py` are asked with barrel
   following on, **Then** only files that import `AuthService` (directly or through the package) are listed.
4. **Given** the chain goes through two packages (`app.py` → `pkg/__init__.py` → `pkg/auth/__init__.py` →
   `pkg/auth/service.py`), **When** dependents of `pkg/auth/service.py` are asked with barrel following on,
   **Then** `app.py` is attached through the full chain, with every import line as evidence.
5. **Given** the same question through the MCP `dependents` tool and through `graphora query`, **Then** the
   answers are identical.

---

### User Story 2 - Renamed imports are followed exactly (Priority: P1)

`pkg/__init__.py` has `from .server import create_server as make_server`. In Python, `from pkg import
make_server` works and `from pkg import create_server` fails. The graph records the bound name `make_server`,
so barrel following attaches the first importer to `server.py` and never the second.

**Why this priority**: Without the bound name the query would have to assume that the name is unchanged and
would be wrong in both directions when `as` is used. Recording it is what lets barrel links be `resolved`
instead of a guess. It is part of the same change as User Story 1.

**Independent Test**: In the `py-barrels` fixture, check the edge of an `as` import carries the bound name, and
that dependents with barrel following attach the importer of the new name and not the importer of the old one.

**Acceptance Scenarios**:

1. **Given** `from .server import create_server as make_server` on line 2 of `pkg/__init__.py`, **When** the
   project is analyzed, **Then** the edge for that line has symbol `create_server` and bound name
   `make_server`.
2. **Given** `cli.py` imports `make_server` from `pkg` and `old.py` imports `create_server` from `pkg`,
   **When** dependents of `pkg/server.py` are asked with barrel following on, **Then** `cli.py` is attached
   through `pkg/__init__.py:2` and `old.py` is not attached to `pkg/server.py`.
3. **Given** a plain import without `as`, **When** the project is analyzed, **Then** its edge carries no bound
   name, exactly as today.

---

### User Story 3 - Impact sees through Python packages (Priority: P2)

A developer asks what can break if `pkg/service.py` changes, with barrel following on. Files that import from
it through the package appear at distance 1, with the barrel link as their chain, as for TS/JS.

**Why this priority**: Impact is already complete without barrel following (the chain passes through
`__init__.py`); barrel following only makes distances and chains shorter and clearer.

**Independent Test**: Run impact with barrel following on the `py-barrels` fixture and compare with
hand-written answers.

**Acceptance Scenarios**:

1. **Given** the files of User Story 1, **When** impact of `pkg/service.py` is asked with barrel following on,
   **Then** `app.py` is at distance 1 with the barrel link as its chain.
2. **Given** barrel following off, **Then** the impact answer is exactly what it is today.

---

### Edge Cases

- `from .service import *` in `__init__.py`: which names it brings depends on `__all__` and on names that may
  be defined by code that is not analyzed. It is not followed; the importer stays attached to `__init__.py`.
- The name is defined in `__init__.py` itself (a function or class): the importer is attached to
  `__init__.py`, not followed further.
- The name is a submodule (`from . import server` in `__init__.py`, then `from pkg import server`): the
  importer is attached to the submodule file.
- The imported file neither defines the name nor imports it (for example a module-level constant, which the
  graph does not list as a definition): the importer is attached to that file, since a resolved import proves
  the name comes from there.
- The import in `__init__.py` is unresolved: it is never followed; the importer stays on `__init__.py`.
- The import in `__init__.py` is `heuristic`: it may be followed, and the derived link is `heuristic`.
- A loop of packages importing each other's names: following stops at a file already on the path.
- Re-imports in an ordinary module, not `__init__.py` (`a.py` has `from b import helper`, `c.py` has
  `from a import helper`): Python allows it, so it is followed the same way.
- A name bound twice in one file (imported, then redefined below): a definition in the file wins; the importer
  is attached to that file.
- TS/JS and C# graphs: answers do not change.

## Requirements *(mandatory)*

### Functional Requirements

**Analyzer**

- **FR-001**: For a Python `from … import name as other` the import edge MUST carry the bound name `other`
  next to the imported name `name`. Imports without `as` MUST carry no bound name.
- **FR-002**: For `import a.b as c` (a whole module) the edge MUST carry the bound name `c`.
- **FR-003**: Python files MUST still carry no export list; nothing else in Python output changes.
- **FR-004**: The graph format version MUST be raised, and every consumer (loader, store, queries, MCP) MUST
  accept the new version in the same change. Graphs of the previous version are rejected with the existing
  "version not supported" message, as for earlier version changes.

**Queries**

- **FR-005**: With barrel following on, a Python file MUST be treated as making a name importable when it
  defines it (a top-level class or function) or imports it explicitly with `from … import`, under its bound
  name (the `as` name if given, else the imported name).
- **FR-006**: When a file imports a name from a Python file that makes it importable only through an import,
  the dependent MUST also be attached to the file the name comes from, following further Python files the
  same way, with every import edge in the chain as evidence. This applies to `dependents` and `impact`.
- **FR-007**: A name imported with `*`, an unresolved import, or a name the chain cannot trace MUST NOT be
  followed; the dependent stays attached to the file it imports from. Nothing is guessed.
- **FR-008**: The confidence of a derived link MUST be the weakest confidence of the edges it rests on, as for
  TS/JS barrel links today.
- **FR-009**: With barrel following off, every answer MUST be byte-identical to the current answer on the
  same graph.
- **FR-010**: TS/JS and C# answers MUST NOT change, with barrel following on or off.
- **FR-011**: The descriptions of the `follow_barrels` option in the CLI help and the MCP tools MUST say that
  it covers Python package re-exports as well as `index.ts`.

**Tests**

- **FR-012**: A new hand-written golden fixture `py-barrels` MUST cover: a re-export through `__init__.py`,
  a chain through two packages, an `as` rename (both the new and the old name imported), a `*` import, a
  submodule import, a name defined in `__init__.py`, and a module-level constant.
- **FR-013**: Existing hand-written `expected.json` files MUST be updated only where a Python import uses `as`.

### Key Entities

- **Bound name**: the name a Python import creates in the importing file: the `as` name, or the imported name
  when there is no `as`. Stored on the edge only when it differs from what is written (when `as` is used).
- **Python barrel**: any Python file that makes a name importable by importing it; most often `__init__.py`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On Graphora's own backend, dependents of `mcp/server.py` with symbol `create_server` and barrel
  following on list all files that import it through `graphora.mcp` (today: 6 files hidden behind
  `mcp/__init__.py`).
- **SC-002**: On the `py-barrels` fixture, every hand-written answer matches, and no importer of a renamed or
  `*`-imported name is attached to a file it cannot reach in Python.
- **SC-003**: All existing golden and query fixtures for TS/JS and C# pass unchanged; Python fixtures differ
  only by the bound name on `as` imports.
- **SC-004**: Analyzing the same snapshot twice gives a byte-identical graph.
- **SC-005**: Barrel following on a 1,000-file Python project stays within the time limits of the existing
  query performance test.

## Assumptions

- The Python adapter belongs to Ulyana and the graph format and `expected.json` files are shared files
  (`docs/product/team-workflow.md`). As in PR #22, the format change goes in this feature's pull request, and
  the pull request needs Ulyana's agreement before merge.
- The analyzer version changes, so stored analyses are made again on the next analysis, as with every
  analyzer change.
- Conditional imports (`try`/`except`, `if TYPE_CHECKING`) are followed like other imports when the analyzer
  already records them as static imports.
- Out of scope: following `*` imports through `__all__`, names assigned by code (`x = y`), and `del`.
