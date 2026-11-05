# Contract: `graphora query`

`graphora analyze` is unchanged. A new subcommand runs one query on a graph document.

```
graphora query <graph> <question> [target] [options]
```

| Argument | Meaning |
|---|---|
| `<graph>` | path to a graph JSON written by `graphora analyze`, or `-` for standard input |
| `<question>` | `dependencies`, `dependents`, `impact`, `neighbors`, `cycles` or `key-files` |
| `[target]` | required for the first four questions, not allowed for `cycles` and `key-files`; a node id, a file path or an external package name (research R10) |

| Option | Questions | Default |
|---|---|---|
| `--format text\|json` | all | `text` |
| `--limit N` | all | none; `10` for `key-files` |
| `--no-type-only` | all | type-only links included |
| `--symbol NAME` | `dependents` | none |
| `--max-depth N` | `impact` | none |
| `--follow-barrels` | `dependents`, `impact` | off |

Output:

- `--format json`: exactly `results.dumps(answer)` on standard output ([answers.md](answers.md)).
- `--format text`: `results.render_text(answer)`. A first line `<question> <target> @ <snapshot>`, then one line per item: path, distance or counts, then the chain
  as `a.py:3 → b.py:7 → target.py`. Heuristic items end with `(likely)`, type-only items with `(type-only)`.
  The last lines give `total`, truncation, `cut` and the completeness note.
- Standard error carries only errors, as `graphora: error: …`.

Exit codes (existing codes keep their meaning; 6 is taken by 005 for an unavailable store, so the query codes are 7
and 8):

| Code | Meaning |
|---|---|
| 0 | answer written (an empty answer is still 0) |
| 2 | usage error: unknown question, missing or extra target, bad option value, unreadable graph file |
| 7 | invalid graph document (`InvalidGraph`): not JSON, wrong schema version, broken references |
| 8 | target not found (`NodeNotFound`); the message names the reason, for example `src/gen.go is detected_only (not analyzed)`, `node_modules is skipped (excluded_dir)` or `x.py is not in snapshot <id>` |

Examples:

```
graphora analyze fixtures/repos/py-flat/repo --out /tmp/g.json
graphora query /tmp/g.json impact pkg/a.py --max-depth 2
graphora query /tmp/g.json dependents lodash --format json
graphora analyze . | graphora query - cycles
```
