# Contract: queries with barrel following

No new options or result fields. `follow_barrels` on `dependents` and `impact` (CLI `--follow-barrels`,
MCP `follow_barrels`) now also follows Python bindings (research § R3).

| Situation (Python) | Importer attached to |
|---|---|
| `pkg/__init__.py`: `from .service import AuthService`; `app.py`: `from pkg import AuthService` | `pkg/service.py`, via `pkg/__init__.py` line |
| chain through two packages | the defining file, every import line in `via` |
| `from .server import create_server as make_server`; importer of `make_server` | `pkg/server.py` |
| same; importer of `create_server` from `pkg` | stays on `pkg/__init__.py` |
| `from .x import *` in `pkg/__init__.py` | stays on `pkg/__init__.py` |
| name defined in `pkg/__init__.py` | `pkg/__init__.py` (no derived link) |
| `from . import server`; importer of `server` from `pkg` | `pkg/server.py` |
| module constant `LIMIT` imported in `pkg/__init__.py` from `pkg/config.py` | `pkg/config.py` |
| unresolved import in `pkg/__init__.py` | stays on `pkg/__init__.py` |

Help text: CLI `--follow-barrels` "dependents and impact: see through re-exports (index.ts, Python imports)";
MCP descriptions say "through index.ts re-exports and Python package imports (`__init__.py`)".

Answers with `follow_barrels` off, and all TS/JS and C# answers, are unchanged.
