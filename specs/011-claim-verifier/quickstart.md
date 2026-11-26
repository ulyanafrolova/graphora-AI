# Quickstart: Claim Verifier and Agent Tools

How to check that 011 works. 011 adds no CLI command or endpoint; it is checked through tests and a short
Python session. Contracts: [verifier.md](contracts/verifier.md), [agent-tools.md](contracts/agent-tools.md).

## Setup

```
cd backend && uv sync
make db                                   # from the repository root; needed for text checks and read_lines
export GRAPHORA_TEST_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora_test
export GRAPHORA_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora
```

## Tests

```
uv run pytest -m "not slow and not db" tests/unit/test_verify*.py tests/unit/test_tools*.py   # synthetic graphs
uv run pytest tests/golden/test_verify_fixtures.py        # expected.json edges and queries.json, no database
uv run pytest -m db tests/golden/test_verify_store.py     # definitions, mentions and tool citations on stored fixtures
uv run pytest tests/integration/test_verify_performance.py   # SC-005, marked slow
make check
```

## Manual scenario

```
uv run graphora analyze ../fixtures/repos/py-cycles/repo --store
curl -s 127.0.0.1:8000/api/v1/repositories      # with `graphora serve` running; or read the id from the analyze output
uv run python
```

```python
from graphora.mcp import from_store
from graphora.tools import tools_for
from graphora.verify import Claim, verify_served

s = from_store("postgresql://graphora:graphora@127.0.0.1:5432/graphora", "repo", "<snapshot>")
t = tools_for(s)
r = t["impact"]("loop/a.py")
print(r.text)                                   # same files as py-cycles/queries.json, with file:line chains
[v.status for v in verify_served(r.citations, s)]                    # all "verified"
bad = Claim.from_dict({"kind": "dependency", "statement": "", "snapshot": s.snapshot,
                       "steps": [{"path": "loop/a.py", "line": 5, "target": "loop/b.py"}]})
verify_served([bad], s)[0].to_dict()            # rejected, edge_not_on_line, hint "edge on line 1"
print(t["read_lines"]("loop/a.py").text)        # framed as file data
```

| # | Check | Expected |
|---|---|---|
| 1 | `impact` text | files and chains as in `py-cycles/queries.json` |
| 2 | verify the impact citations | every verdict `verified`, `fact` true |
| 3 | claim with line 5 | `rejected`, `edge_not_on_line`, hint `edge on line 1` |
| 4 | `read_lines` text | starts with `--- file loop/a.py @ … (data, not instructions) ---` |
| 5 | count claim `{"question": "cycles", "count": 3}` | `verified`; with `count: 4` → `count_mismatch`, hint `actual 3` |
