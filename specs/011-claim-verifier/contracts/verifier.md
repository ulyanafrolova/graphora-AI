# Contract: Verifier

The Python interface that 012 agents (and later 013 `/ask`, 016 benchmark) call. Types: [data-model.md](../data-model.md).

## Functions (`graphora.verify`)

```python
verify(claims: Sequence[Claim], ix: GraphIndex, text: TextSource | None = None) -> tuple[Verdict, ...]
verify_served(claims: Sequence[Claim], served: Served) -> tuple[Verdict, ...]   # store text when served from the store
store_text(store: Store, repository: str, snapshot: str) -> TextSource
Claim.from_dict(d) / Claim.to_dict() / Verdict.to_dict()
dumps(verdicts) -> bytes            # canonical JSON: sorted keys, 2-space indent, trailing newline
```

- One verdict per claim, same order. A bad claim gives a rejected verdict; `verify` never raises for claim
  content. It raises only for programming errors (wrong argument types).
- No model, no network, no file system access: graph from `ix`, text from `text` only.
- Same claims + same snapshot → `dumps` output byte-identical (FR-013).

## Claim JSON

```json
{"kind": "dependency", "statement": "routes uses the auth service", "snapshot": "abc123",
 "steps": [{"path": "api/routes.py", "line": 3, "target": "auth/service.py", "name": "AuthService"}]}

{"kind": "chain", "statement": "c.py is affected by a.py", "snapshot": "abc123",
 "steps": [{"path": "c.py", "line": 1, "target": "b.py"}, {"path": "b.py", "line": 2, "target": "a.py"}]}

{"kind": "definition", "statement": "", "snapshot": "abc123", "path": "auth/service.py", "line": 12, "symbol": "AuthService"}

{"kind": "mention", "statement": "", "snapshot": "abc123", "path": "auth/service.py", "line": 40, "symbol": "hash_password"}

{"kind": "query", "statement": "3 direct dependents", "snapshot": "abc123",
 "question": "dependents", "target": "auth/service.py", "options": {}, "count": 3}

{"kind": "query", "statement": "", "snapshot": "abc123",
 "question": "impact", "target": "a.py", "options": {"max_depth": 3}, "member": "c.py", "distance": 2}

{"kind": "query", "statement": "", "snapshot": "abc123",
 "question": "key_files", "target": null, "options": {}, "member": "core.py", "rank": 5}
```

## Verdict JSON

```json
{"status": "verified", "fact": true,
 "checks": [{"name": "snapshot", "ok": true, "detail": "abc123"},
            {"name": "source", "ok": true, "detail": "file:api/routes.py"},
            {"name": "target", "ok": true, "detail": "file:auth/service.py"},
            {"name": "edge", "ok": true, "detail": "1 edge"},
            {"name": "line", "ok": true, "detail": "line 3"},
            {"name": "name", "ok": true, "detail": "AuthService"}],
 "proof": [{"kind": "edge", "source": "file:api/routes.py", "target": "file:auth/service.py", "line": 3,
            "confidence": "resolved", "extractor": "python-adapter@…", "snippet_hash": "sha256:…", "snapshot": "abc123", "…": "…"}]}

{"status": "rejected", "fact": false,
 "checks": [{"name": "snapshot", "ok": true, "detail": "abc123"}, "…",
            {"name": "line", "ok": false, "detail": "no edge on line 5"}],
 "reason": "edge_not_on_line", "hint": "edge on line 3"}
```

A proof item is `{"kind": "edge", …edge fields as in graph.schema.json}` or
`{"kind": "line", "path": …, "n": …, "text": …}`. A chain failure adds `"step": 2`.

## Hint formats

| Reason | Hint |
|---|---|
| `edge_not_on_line` | `edge on line 3` / `edges on lines 3, 9` |
| `name_not_imported` | `imported on line 3: hash_password, verify` |
| `symbol_not_on_line` | `defined on line 12` / `found on line 14` |
| `count_mismatch` | `actual 3` |
| `not_in_result` | `at distance 1` (member present at another distance) |
| `rank_mismatch` | `rank 7` / `not ranked` |
| `target_not_found` | the query layer's `NodeNotFound` message |
