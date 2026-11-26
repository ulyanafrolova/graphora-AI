# Contract: backend additions of 019

## Query layer

```python
queries.components(ix: GraphIndex, *, include_type_only: bool = True) -> Answer
queries.cycles(ix, *, include_type_only=True, limit=None, level="file") -> Answer   # each file-level group gains `cut`
```

`components` answer (`results.dumps`, abbreviated):

```json
{
  "question": "components",
  "snapshot": "content:…",
  "target": null,
  "options": {"include_type_only": true},
  "total": 3,
  "truncated": false,
  "components": [
    {"id": "component:1", "name": "src/auth", "files": ["file:src/auth/service.py", "…"], "file_count": 4, "has_cycle": true}
  ],
  "links": [
    {"source": "component:1", "target": "component:2", "imports": 6, "heuristic": 0, "in_cycle": true}
  ],
  "completeness": {"unresolved_imports": 0, "not_analyzed_files": 0, "files_with_errors": 0}
}
```

`cycles` group with a cut:

```json
{
  "files": ["file:loop/a.py", "file:loop/b.py", "file:loop/c.py"],
  "cycle": [ {"source": "file:loop/a.py", "target": "file:loop/b.py", "…": "…"} ],
  "type_only": false,
  "confidence": "resolved",
  "cut": {"method": "exact", "links": [ {"source": "file:loop/c.py", "target": "file:loop/a.py", "edges": ["…"]} ]}
}
```

Text rendering adds one line per group: `cut (exact): loop/c.py:3 → loop/a.py`.

## CLI

`graphora query <graph> components [--no-type-only] [--format json|text]` (no target, no `--limit`). `cycles` output
gains the cut line / field.

## MCP

New tool `components(include_type_only: bool = True)`, read-only, description in `DESCRIPTIONS`. `cycles` results gain
`cut`. Structured content equals the CLI JSON.

## HTTP

| Route | Parameters | Body |
|---|---|---|
| `GET /api/v1/components` | `repository`, `snapshot`, `include_type_only` | = `graphora query … components --format json` |
| `GET /api/v1/cycles` (018) | unchanged | now includes `cut` |
| `GET /api/v1/files` | `repository`, `snapshot` | `{"repository", "snapshot", "files": [{"path", "has_text", "line_count"}]}` sorted by path |
| `GET /api/v1/info` | none | `{"version", "ask": {"enabled", "model"}, "jobs": {"enabled"}, "mcp_tools": [{"name", "description"}]}` |

Errors as 018: 400 parameters, 404 missing repository/snapshot, 409 `stale`.

## Serving the UI

- `graphora serve --ui DIR`; default `$GRAPHORA_UI_DIR`, else `<repository>/frontend/dist` if it exists.
- With a UI: `GET /` and any `GET` outside `/api/` → a file of DIR if it exists, else `DIR/index.html` (200).
  Responses for UI files carry `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'
  'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'`.
- `/api/...` unknown paths: JSON 404 `no such endpoint`, as before.
- Without a UI: unchanged behaviour (`GET /` → JSON 404).
