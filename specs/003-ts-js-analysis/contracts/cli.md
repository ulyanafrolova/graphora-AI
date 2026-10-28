# CLI Contract: `graphora analyze` (changes in 003)

The command, its arguments, exit codes, atomic writing and safety rules are unchanged from
[001 contracts/cli.md](../../001-python-graph-cli/contracts/cli.md). This file lists only what 003 changes.

```
graphora analyze <dir> [--out <file>] [--max-files N] [--max-bytes N] [--max-seconds N]
```

No new arguments. TS/JS analysis is always on.

## Behaviour changes

- **Output.** The graph document validates against `schema/graph.schema.json` **v2**
  ([graph.schema.json](graph.schema.json)) and has `"schema_version": 2`. That holds for every repository,
  including Python-only ones.
- **Analyzed files.** `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs` and `.cjs` files are parsed and
  count as `analyzed` in coverage. They count toward `--max-files` and `--max-bytes` exactly as before (all
  non-skipped files already counted).
- **Configuration files.** `tsconfig.json` and `jsconfig.json` are read as JSON-with-comments data. Their
  `extends` chain is followed only inside `<dir>`. `package.json` files are read only for their `name`
  field. Nothing they name is run, and `node_modules` is never read (it is skipped).
- **Summary line.** Unchanged format, and counts include TS/JS:
  `graphora: info: analyzed N files, E edges (U unresolved), snapshot <id>`.
- **Warnings.** A config file that cannot be read gives one stderr line:
  `graphora: warning: ignoring <path>: not valid JSON-with-comments`. The exit status stays `0`, and the
  coverage entry gets `parse_error`.

## Exit codes

Unchanged: `0` when a graph is produced, `2` for usage errors, `3` when a limit is exceeded.

## Examples

```
$ graphora analyze fixtures/repos/ts-app/repo --out /tmp/ts-app.json
graphora: info: analyzed 21 files, 38 edges (5 unresolved), snapshot content:…

$ graphora analyze fixtures/repos/mixed-fullstack/repo | jq '[.nodes[] | select(.kind=="external") | .id]'
["ext:npm:react", "ext:npm:yaml", "ext:python:requests", "ext:python:yaml"]
```

The counts are illustrative. The fixture's `expected.json` is the ground truth.
