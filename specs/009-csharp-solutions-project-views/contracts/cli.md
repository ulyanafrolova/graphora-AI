# CLI, MCP and HTTP Contract Changes: C# Analysis, Slice 3

Contracts of 001–008 apply with these changes.

## `graphora analyze`

- Output is schema v6 ([graph.schema.json](graph.schema.json)). Warnings gain `.sln`/`.slnx` files with
  `parse_error`: `ignoring <path>: not a readable solution file`.

## `graphora query`

```
graphora query <graph> projects [--format text|json]
graphora query <graph> dependencies|dependents|impact|cycles [<target>] --level project [--limit N] [--max-depth N]
```

- `--level` takes `file` (default, unchanged behaviour) or `project`.
- At project level `<target>` is a `project:` id, a `.csproj` path or a C# file path (mapped to its project).
  `--symbol`, `--follow-barrels` and `--no-type-only` are usage errors at project level (exit 2, existing message
  format).
- Text output of a project link: `<project>  <first evidence file>:<line> (+N more) → <target>`; declared-only
  links end in `(declared, not used by code)`; "likely" as before.
- JSON: the existing answer shape; links may carry `declared` (list of edges); items may carry `declared_only: true`;
  the `projects` answer has a `projects` list (data-model.md § Projects answer entry).
- Not-a-project targets: the existing not-found exit status (8) with `… is not a project` (status `not_a_project`).

## MCP

- New tool `projects` (no arguments): same answer as the CLI `projects` question.
- `dependencies`, `dependents`, `impact`, `cycles` gain `level` (`"file"` | `"project"`, default `"file"`).
- `graph_overview`: `schema_version` 6; `nodes` gains `solution`.
- Answers are byte-identical to the CLI JSON (existing golden test).

## HTTP API

- `/graph` serves v6 documents (solution nodes included). No new endpoints.
