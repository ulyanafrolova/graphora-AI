# Contract: CLI changes

## `graphora mcp` (new)

```
graphora mcp --graph <file>
graphora mcp --repository <name> --snapshot <id> [--database <url>]
```

| Option | Meaning |
|---|---|
| `--graph FILE` | serve a graph JSON written by `graphora analyze`; `-` is rejected (standard input is the protocol) |
| `--repository`, `--snapshot` | serve a stored analysis (feature 005); both required together |
| `--database URL` | store mode only; default `$GRAPHORA_DATABASE_URL` |

Exactly one source must be given. The command runs until the client closes standard input.

| Code | Meaning |
|---|---|
| 0 | client closed the connection |
| 2 | usage: no source, both sources, `--graph -`, `--database` without store mode, unreadable graph file |
| 6 | store unavailable (as `serve`) |
| 7 | invalid graph document (as `query`) |
| 8 | stored pair not found: `repository not found: R` or `snapshot not found: R S` |

Standard output carries only protocol messages. Errors are printed as `graphora: error: …` on standard error.

## `graphora query` (two new questions)

```
graphora query <graph> definitions <name> [--limit N] [--format text|json]
graphora query <graph> overview [--format text|json]
```

- `definitions` takes the name as its target; the name is not resolved as a node.
- `overview` takes no target and no options except `--format`.
- Other options (`--symbol`, `--max-depth`, `--follow-barrels`, `--no-type-only`) are usage errors for both.
- Exit codes as in `specs/004-graph-queries/contracts/cli.md`.
