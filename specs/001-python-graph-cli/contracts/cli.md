# CLI Contract: `graphora analyze`

```
graphora analyze <dir> [--out <file>] [--max-files N] [--max-bytes N]
```

| Argument | Default | Meaning |
|---|---|---|
| `<dir>` | required | The folder to analyze. It must exist and be a directory, and it is read only |
| `--out <file>` | standard output | Where to write the graph document. The path must not be inside `<dir>` |
| `--max-files N` | `5000` | Maximum number of files that are not skipped |
| `--max-bytes N` | `52428800` (50 MB) | Maximum total size, in bytes, of the files that are not skipped |

## Behaviour

- **Output.** On success the command writes exactly one graph document that validates against
  `schema/graph.schema.json` v1 (see [graph.schema.json](graph.schema.json)). It uses UTF-8 and LF line
  endings and ends with a single trailing newline.
- **Writing `--out`.** The file is written atomically, through a temp file in the same folder and then a
  rename. On any failure no file is created or changed at `--out`.
- **Standard error.** Diagnostics go to stderr as lines of the form `graphora: <level>: <message>`. On
  success there is one summary line: `graphora: info: analyzed N files, E edges (U unresolved), snapshot
  <id>`. Stderr content is not part of the determinism guarantee.
- **The analyzed folder.** Nothing is executed, imported or installed from `<dir>`, no `git` subprocess is
  started, and nothing inside `<dir>` is written.

## Exit codes

| Code | When |
|---|---|
| `0` | A graph was produced, even if it has unresolved edges, parse errors or no Python files |
| `2` | A usage error: `<dir>` is missing or is not a folder, `--out` is inside `<dir>`, or the output cannot be written |
| `3` | A limit was exceeded. The message names the limit, its value and the observed count |

## Examples

```
$ graphora analyze fixtures/repos/py-flat/repo --out /tmp/flat.json
graphora: info: analyzed 9 files, 14 edges (3 unresolved), snapshot content:5e1c…

$ graphora analyze ./proj --max-files 10
graphora: error: file limit exceeded: 42 files > --max-files 10
$ echo $?
3
```

The counts in the first example are illustrative.
