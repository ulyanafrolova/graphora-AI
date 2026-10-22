# Data Model: Python Import Graph CLI

The serialized form is defined by [contracts/graph.schema.json](contracts/graph.schema.json), which becomes
`schema/graph.schema.json`. This file explains the meaning of each part and the rules behind it.

All paths are POSIX paths relative to the analyzed folder. They never start with `/` or `./` and never
contain `..`.

## GraphDocument (root)

| Field | Type | Rule |
|---|---|---|
| `schema_version` | integer | Always `1` in this slice |
| `snapshot` | string | See Snapshot |
| `extractors` | object | Component name → version. Example: `{"python-adapter": "0.1.0", "python-resolver": "0.1.0", "python-stdlib": "3.14.0"}` |
| `nodes` | Node[] | Sorted by `id`. Ids are unique |
| `edges` | Edge[] | Sorted by `(source, line, column, target, symbol ?? "")` |
| `coverage` | Coverage | |

## Snapshot

The snapshot is a string in one of three forms, decided in this order:

1. If `<dir>/.git` is a directory, HEAD resolves to a commit, and the working blob map equals the HEAD blob
   map, the id is the 40-hex commit SHA.
2. If `<dir>/.git` is a directory and the maps differ, the id is `<40-hex sha>+dirty:<16-hex content
   hash>`.
3. In every other case the id is `content:<16-hex content hash>`. This covers no `.git`, a `.git` file, an
   unborn HEAD and a corrupt repository.

The blob maps are explained in [research.md § R3](research.md), and the content hash in § R4.

Regex for the snapshot id: `^([0-9a-f]{40}(\+dirty:[0-9a-f]{16})?|content:[0-9a-f]{16})$`.

## Node

Every node has `id` and `kind`. The fields depend on the kind.

| Kind | Id | Other fields |
|---|---|---|
| `file` | `file:<path>` | `path`, `language: "python"`, `definitions: Definition[]` |
| `external` | `ext:<top-level name>` | `name`, `category: "stdlib" \| "third_party"` |
| `unresolved` | `unresolved:<reference>` | `reference` |

These rules apply to nodes:

- A file node exists for every coverage entry with status `analyzed`, including files with parse errors.
- An external node or an unresolved node exists only when at least one edge points to it.
- The unresolved `reference` is one of:
  - the absolute dotted name, when the base package of a relative import is known (for example
    `pkg.missing`);
  - otherwise, the import expression exactly as written in the source (for example `...x` or
    `importlib.import_module(name)`).

### Definition (attribute of a file node)

| Field | Type | Rule |
|---|---|---|
| `kind` | `class` \| `function` \| `method` | `function` covers `def` and `async def` at module level. `method` covers `def` and `async def` directly in the body of a module-level class |
| `name` | string | Qualified name: `Foo`, `bar`, `Foo.baz` |
| `line` | integer ≥ 1 | Line of the `def` or `class` keyword, not of a decorator |

Definitions are sorted by `(line, name)`. Nested functions, nested classes and definitions inside `if` or
`try` blocks at module level are not listed in this slice.

## Edge

| Field | Type | Rule |
|---|---|---|
| `id` | string | `e:` + the first 16 hex of SHA-256 over `source\|line\|column\|target\|symbol` |
| `source` | node id | Always a `file:` node |
| `target` | node id | A `file:`, `ext:` or `unresolved:` node |
| `type` | `"imports"` | The only edge type in schema v1 |
| `symbol` | string \| null | The name imported by `from … import`, or `*`. `null` for `import x` and for dynamic imports |
| `line` | integer ≥ 1 | Start line of the import statement or call |
| `column` | integer ≥ 1 | Start column of the statement or call, counted in Unicode code points (1-based) |
| `snapshot` | string | Equals the document's `snapshot` |
| `confidence` | `resolved` \| `heuristic` \| `unresolved` | `heuristic` is allowed by the schema but never emitted in this slice |
| `reason` | string \| absent | Required exactly when `confidence = unresolved`. One of `not_found`, `relative_beyond_top`, `namespace_package`, `dynamic` |
| `extractor` | string | `python-adapter@0.1.0` |
| `snippet_hash` | string | `sha256:<16 hex>`, see research § R4 |

These rules apply to edges:

- `from m import a, b` produces two edges with the same line and column and different `symbol` values. The
  pair `(line, column, symbol)` keeps edge ids unique.
- `confidence = resolved` exactly when the target is a `file:` or `ext:` node.
- `confidence = unresolved` exactly when the target is an `unresolved:` node.

## Coverage

| Field | Type | Rule |
|---|---|---|
| `files` | CoverageFile[] | Every walked file that is not skipped, sorted by `path` |
| `skipped` | Skipped[] | Each skipped folder (once, not its contents) and each skipped file, sorted by `path` |
| `summary` | object | `{analyzed, detected_only, not_code, skipped}` counts, plus `by_language` (language → count, keys sorted) |

### CoverageFile

| Field | Type | Rule |
|---|---|---|
| `path` | string | |
| `language` | string \| null | From the extension table, or from the marker-file table (`pyproject.toml`, `setup.py` and `setup.cfg` → `python`; `package.json` and `tsconfig.json` → `typescript`; `go.mod` → `go`; `Cargo.toml` → `rust`; `pom.xml` and `build.gradle` → `java`) |
| `status` | `analyzed` \| `detected_only` \| `not_code` | `.py` and `.pyi` files are `analyzed`. Other files with a programming-language extension are `detected_only`. Everything else, including marker files, is `not_code` |
| `flags` | string[] | Sorted. Possible values: `parse_error` (the tree has ERROR or MISSING nodes) and `unreadable` (the Python file cannot be decoded, so it gets no edges and no definitions) |

`detected_only` extensions in this slice:

| Language | Extensions |
|---|---|
| typescript | `.ts`, `.tsx`, `.mts`, `.cts` |
| javascript | `.js`, `.jsx`, `.mjs`, `.cjs` |
| go | `.go` |
| java | `.java` |
| kotlin | `.kt`, `.kts` |
| rust | `.rs` |
| csharp | `.cs` |
| c | `.c`, `.h` |
| cpp | `.cpp`, `.cc`, `.hpp` |
| ruby | `.rb` |
| php | `.php` |
| swift | `.swift` |
| scala | `.scala` |
| shell | `.sh` |

### Skipped

| Field | Type | Rule |
|---|---|---|
| `path` | string | |
| `reason` | string | One of the reasons below |

| Reason | When it applies |
|---|---|
| `excluded_dir` | The folder name is in FR-009 |
| `nested_repository` | A folder below the root that contains `.git` |
| `symlink` | A file or folder symlink. It is never followed |
| `minified` | A file named `*.min.js` or `*.min.css` |

Skipped items do not count toward the limits and are not included in the content hash.

## Resolution

**Inputs.** The resolver takes the set of analyzed file paths. Source roots are `R = ["", "src"]`, and
`src` is included only if it is a folder. For each root `r`, a file `p` under `r` has the module name
`p` with these changes: drop the `r/` prefix, drop the `.py` or `.pyi` suffix, replace `/` with `.`, and
strip a trailing `.__init__`.

**Module index.** The index maps a dotted name to a file path. Roots are searched in order, and the first
root that has the name wins. Within one root, `.py` wins over `.pyi`.

**Namespace packages.** The set `NS` holds dotted names of folders that have Python descendants but no
`__init__`.

**Locality.** A top-level name `t` is local when `t` is in the index or in `NS` for some root.

**Home root and base package.** A file's *home root* is the most specific root containing it, so a file
under `src/` uses `src`. Its *module name* is computed under that root. Its *package* is:

- for an `__init__` file, the module name;
- otherwise, the module name with its last part removed.

| Import | Result |
|---|---|
| `import a.b.c` | The edge goes to the index entry for `a.b.c` if there is one. Otherwise, if `a.b.c` is in `NS` the reason is `namespace_package`. Otherwise, if `a` is local the reason is `not_found`. Otherwise the edge goes to `ext:a` |
| `from M import n` (absolute) | Resolve `M` as above. If `M.n` is in the index, the edge goes to it, with symbol `n`. Otherwise, if `M` is a file, the edge goes to it, with symbol `n`. Otherwise, if `M` is in `NS` and `M.n` is not in the index, the reason is `not_found`. If `M` is external, the edge goes to `ext:<top of M>`, with symbol `n` |
| `from .X import n` (level k) | The base is the file's package with `k-1` trailing parts removed. If there are not enough parts, or the package is empty, the reason is `relative_beyond_top`. Otherwise `M` is `base.X` (or `base` when `X` is empty) and is resolved like an absolute import, with one difference: a missing local name is never external. It gets reason `not_found`, and the reference is the dotted name |
| `importlib.import_module("a.b")`, `import_module("a.b")`, `__import__("a.b")` | Resolved like `import a.b`, with symbol `null` |
| The same calls with a non-literal argument, an f-string, a concatenation, a literal starting with `.`, or a `package=` argument | Reason `dynamic`, and the reference is the call text exactly as written |

**Recognising dynamic imports.** A bare `import_module(...)` call counts as a dynamic import only if the
file contains `from importlib import import_module`. Aliases from `import importlib as il` are recognised
too.

**Which imports are recorded.** Imports in every scope are recorded: in functions, under `if TYPE_CHECKING`
and inside `try` blocks.

## State

There is no persistent state. One run maps one folder to one `GraphDocument`.
