# Contract: `graphora ask`

```
graphora ask QUESTION (--graph FILE | --repository NAME --snapshot ID [--database URL])
             [--model PROVIDER:MODEL] [--no-summary] [--json] [--trace FILE]
```

| Option | Meaning |
|---|---|
| `QUESTION` | one positional argument; empty after stripping → usage error |
| `--graph`, `--repository`, `--snapshot`, `--database` | same rules and messages as `graphora mcp` (006 contracts/cli.md); `--graph -` is allowed here (stdin is free) |
| `--model` | overrides `$GRAPHORA_MODEL`; default `ollama:qwen3:8b` |
| `--no-summary` | no summary model call; summary is the code summary |
| `--json` | print `Run.to_dict()` (answer and trace) as sorted JSON instead of text |
| `--trace FILE` | also write the trace as JSON lines to FILE (`-` = stderr) |

## Output

- stdout: `render_answer(answer)` (text) or the JSON document. Nothing else.
- stderr: `graphora: error: …` / `graphora: warning: …` lines, as the other commands.

## Exit codes

| Code | When |
|---|---|
| 0 | an answer was printed, whatever its end reason, except `model_failed` before any claim |
| 2 | usage error |
| 6 | store unavailable |
| 7 | invalid graph |
| 8 | repository or snapshot not found |
| 9 | model unavailable: unknown provider, missing integration package, cannot connect, model not pulled; also `model_failed` with no claims. Message: `graphora: error: model ollama:qwen3:8b unavailable at http://127.0.0.1:11434: <reason>` |
| 130 | interrupted |

No traceback is printed for codes 2–9.
