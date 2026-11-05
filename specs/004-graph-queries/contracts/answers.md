# Contract: Answer JSON

Written by `graphora.graph.results.dumps`: UTF-8, keys sorted, two-space indent, trailing newline. Byte-identical
for the same graph and query (FR-015). Types and order: [data-model.md](../data-model.md).

Edge objects are exactly the edge objects of the graph document (same fields, same `id`), so a consumer can
look up every cited edge by `id`.

## Common fields

```json
{
  "snapshot": "3f2a…",
  "question": "impact",
  "target": "file:pkg/a.py",
  "options": {"follow_barrels": false, "include_type_only": true, "limit": null, "max_depth": 2},
  "total": 2,
  "truncated": false,
  "completeness": {"files_with_errors": 0, "not_analyzed_files": 1, "unresolved_imports": 3}
}
```

`target` is `null` for `cycles` and `key_files`. `completeness` is absent for `cycles`.

## Link and item

```json
{
  "node": "file:pkg/c.py",
  "kind": "file",
  "distance": 2,
  "confidence": "resolved",
  "type_only": false,
  "chain": [
    {"source": "file:pkg/c.py", "target": "file:pkg/b.py", "confidence": "resolved", "type_only": false,
     "edges": [{"id": "e:…", "source": "file:pkg/c.py", "target": "file:pkg/b.py", "line": 1, "…": "…"}],
     "via": []},
    {"source": "file:pkg/b.py", "target": "file:pkg/a.py", "confidence": "resolved", "type_only": false,
     "edges": [{"id": "e:…", "line": 2, "…": "…"}], "via": []}
  ]
}
```

- `distance` only in impact items; `transitive_dependents` and `direct_dependents` only in key-file items
  (their `chain` is empty).
- Every chain is a connected walk: each link's `target` is the next link's `source`; the last `target` is the
  answer's `target` (impact, dependents) or the item's `node` (dependencies).
- A barrel link has a non-empty `via` and its `target` is the defining file.

## Per question

| Question | Extra fields |
|---|---|
| `dependencies` | `items`, `unresolved` (list of edge objects) |
| `dependents` | `items` |
| `impact` | `items`, `cut` |
| `neighbors` | `incoming`, `outgoing`, `unresolved` |
| `cycles` | `groups`: `[{"files": [...], "cycle": [link, ...], "type_only": bool, "confidence": "..."}]` |
| `key_files` | `items` |

## Golden projection (`fixtures/repos/<name>/queries.json`)

Hand-written, no hashes (research R12):

```json
[
  {"question": "impact", "target": "pkg/a.py", "options": {"max_depth": 2},
   "expected": {"items": [{"node": "file:pkg/b.py", "distance": 1, "chain": ["pkg/b.py:2"]},
                          {"node": "file:pkg/c.py", "distance": 2, "chain": ["pkg/c.py:1", "pkg/b.py:2"]}],
                "cut": false}}
]
```

A chain is projected to `"<source path>:<line>"` per link, using the first edge of the link; barrel links add
the `via` edges the same way. Cycle groups are projected to `{"files": [...], "cycle": [...], "type_only": …}`.
