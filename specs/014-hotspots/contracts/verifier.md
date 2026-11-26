# Contract: hotspot claims in the claim verifier

These are extensions of specs/011-claim-verifier/contracts/verifier.md. Existing claims and verdicts are
unchanged.

## Claim

```json
{
  "kind": "query",
  "statement": "auth/service.py is the top hotspot with 47 commits and bus factor 1",
  "snapshot": "3f1c…",
  "question": "hotspots",
  "options": {"include_type_only": true},
  "member": "auth/service.py",
  "rank": 1
}
```

```json
{"kind": "query", "statement": "…", "snapshot": "3f1c…", "question": "hotspots",
 "member": "auth/service.py", "metric": "commits", "value": 47}
```

```json
{"kind": "query", "statement": "…", "snapshot": "3f1c…", "question": "hotspots", "count": 14}
```

Validation (otherwise the verdict is `rejected`, `invalid_claim`):

- `hotspots` takes no `target`; the only option allowed is `include_type_only`.
- Exactly one of `count` or `member`.
- `rank` is allowed for `key_files` and `hotspots`; `metric` only for `hotspots`. Both need a `member`.
- `metric` and `value` go together. `metric` is one of `commits`, `authors`, `score`, `transitive_dependents`,
  `direct_dependents`, and `value` is an integer ≥ 0.
- `rank` and `metric` may both be given. Both are then checked.

## Checks and verdicts

The verifier runs `queries.hotspots(ix, include_type_only=…, limit=None)` and then checks in this order:

| Case | Verdict |
|---|---|
| History `not_available` | `rejected`, `history_unavailable`, hint `<reason>` |
| `count` ≠ total | `rejected`, `count_mismatch`, hint `actual N` |
| Member does not resolve | `rejected`, `target_not_found` |
| Member not a hotspot | `rejected`, `not_in_result`; with `rank`: `rank_mismatch`, hint `not ranked` |
| `rank` given and actual position > `rank` | `rejected`, `rank_mismatch`, hint `rank N` (same "within" rule as `key_files`) |
| `metric` value ≠ actual | `rejected`, `count_mismatch`, hint `actual N` |
| Otherwise | accepted, status below |

The status of an accepted claim:
- `heuristic` if the history is `partial`, or if any of the member's dependents is reached only through a
  heuristic link (same rule as the `key_files` rank);
- otherwise `verified`.

Checks list, as in 011:
- `query` (`hotspots total N`);
- `member`;
- `rank`, if given;
- `metric` (`commits 47`), if given;
- `history` (`available`, or `partial: N commits read`).

## Determinism

Verdicts on a non-partial history are identical across runs. Verdicts on a partial history are identical for the
same stored graph: they are checked against the stored summary, not by reading history again.
