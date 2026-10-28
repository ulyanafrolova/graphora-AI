# Data Model: TypeScript/JavaScript Analysis (Graph Schema v2)

The serialized form is defined by [contracts/graph.schema.json](contracts/graph.schema.json), which replaces
`schema/graph.schema.json`. This file describes what changes from the
[001 data model](../001-python-graph-cli/data-model.md) and adds the TS/JS rules. Anything not mentioned
here (snapshot, coverage structure, path rules, Python resolution) is unchanged.

## GraphDocument (root)

| Field | Change |
|---|---|
| `schema_version` | Always `2` |
| `extractors` | Adds `js-adapter`, `js-resolver` and `node-builtins`, for example `{"js-adapter": "0.1.0", "js-resolver": "0.1.0", "node-builtins": "24.0.0", "python-adapter": "0.2.0", "python-resolver": "0.2.0", "python-stdlib": "3.14.0"}`. Both Python versions are bumped because their output changes (new edge fields, ecosystem ids). All six are always present, even when a repository has no files of one language |
| `edges` | Sorted by `(source, line, column, target, symbol ?? "", alias ?? "", type)` |

## Node

| Kind | Id | Other fields |
|---|---|---|
| `file` | `file:<path>` | `path`, `language`, `definitions`; TS/JS also have `exports` |
| `external` | `ext:<ecosystem>:<name>` | `name`, `ecosystem`, `category` |
| `unresolved` | `unresolved:<ecosystem>:<reference>` | `reference`, `ecosystem` |
| `asset` | `asset:<path>` | `path` |

- `ecosystem` is `python` or `npm`. It is decided by the importing file's language: Python gives `python`,
  and TypeScript or JavaScript give `npm`.
- `category` is `stdlib` or `third_party` for `python`, and `builtin` or `third_party` for `npm`.
- An asset node exists only when an edge points to it. Its path is an included, non-skipped file whose
  coverage status is not `analyzed`.

### File node

| Field | Rule |
|---|---|
| `language` | `python`, `typescript` or `javascript`, the same value as the coverage entry |
| `definitions` | Definition[], sorted by `(line, name)` |
| `exports` | TS/JS only. Export[], sorted by `(name, line)` |

### Definition

| Field | Rule |
|---|---|
| `kind` | `class`, `function`, `method`, `interface`, `type_alias` or `enum` |
| `name` | Qualified name, for example `Logger`, `Logger.write` or `default` |
| `line` | Line of the declaring keyword (`class`, `function`, `interface`, `type`, `enum`, the `const`/`let` of an arrow function, or the method name), never of a decorator or of `export` on an earlier line |
| `exported_as` | TS/JS only. Sorted, unique list of the names this definition is exported under. Empty if it is not exported |

**Which TS/JS declarations are definitions.** Only declarations at the top level of the file, or directly
inside a top-level `export` statement:

| Declaration | Kind | Name |
|---|---|---|
| `class C` / `abstract class C` | `class` | `C` |
| `function f` / `function* f` / `async function f` | `function` | `f` |
| `declare function f(…)` and overload signatures | `function` | `f`. Only the first line per name is kept |
| `const f = () => …` / `const f = function …` (also `let`) | `function` | `f`. One definition per declarator whose value is an arrow function or a function expression |
| `interface I` | `interface` | `I` |
| `type T = …` | `type_alias` | `T` |
| `enum E` / `const enum E` | `enum` | `E` |
| Method, getter or setter directly in a top-level class body | `method` | `C.m`. A getter/setter pair with the same name gives one entry, at the first line |
| `export default class {}` / `export default function () {}` | `class` / `function` | `default` |

Not listed: nested functions, namespaces (`namespace N {}`), `declare module` blocks, class fields, and
abstract method signatures.

**How `exported_as` is filled:**

- `export class C` / `export function f` / `export const f = …` add `C` / `f`.
- `export default class C` adds `default` to `C`.
- `export { f }`, `export { f as g }` and `export default f`, where `f` is a definition in the same file,
  add `f`, `g` and `default`.
- Re-exports from another module (`export … from`) never touch definitions. They are edges.

### Export (attribute of a TS/JS file node)

These are exported names that are **not** backed by a definition in the same file:

| Field | Type | Rule |
|---|---|---|
| `name` | string | The exported name, for example `x` or `default` |
| `local` | string \| null | The local binding it exports. `null` for an anonymous `export default <expression>` |
| `line` | integer ≥ 1 | Line of the `export` keyword |

Examples:

- `export const x = 1` gives `{x, x}`.
- `import { a } from "./m"; export { a as b }` gives `{b, a}`.
- `export default router` gives `{default, router}`.
- `export default { … }` gives `{default, null}`.

**The invariant:** every name a TS/JS file exports appears exactly once: either in one definition's
`exported_as`, or in `exports`, or as the alias or symbol of one of its `reexports` edges.

## Edge

| Field | Change |
|---|---|
| `id` | `e:` + 16 hex of SHA-256 over `source\|line\|column\|target\|symbol\|alias\|type`, with `""` for null values |
| `target` | A `file:`, `ext:`, `unresolved:` or `asset:` node |
| `type` | `imports` or `reexports` |
| `form` | `static`, `dynamic` or `require`. A Python `import`/`from` statement is `static`, and `importlib`/`__import__` calls are `dynamic` |
| `type_only` | Boolean. `true` for `import type`, for an inline `type` specifier, and for `export type … from`. Always `false` for Python |
| `alias` | Only on `reexports`. The exported name when it differs from `symbol` (`export { a as b }` gives `b`), or the namespace name for `export * as ns` |
| `reason` | Adds `workspace_package` |
| `extractor` | `js-adapter@0.1.0` for TS/JS edges, `python-adapter@0.2.0` for Python edges |

These rules are new:

- A `reexports` edge always has `form: static`.
- `confidence = resolved` exactly when the target is a `file:`, `ext:` or `asset:` node.
- An edge's source and an unresolved target always share an ecosystem. A file's language fixes the
  ecosystem of every node it creates.

Edge examples for TS/JS:

| Statement in `src/app.ts` | Edges |
|---|---|
| `import { a, b } from "./m"` | two edges to `file:src/m.ts`, symbols `a` and `b` |
| `import type { T } from "./t"` | one edge, symbol `T`, `type_only: true` |
| `export * as ns from "./lib"` | one `reexports` edge, symbol `*`, alias `ns` |
| `const c = require("lodash/fp")` | one edge to `ext:npm:lodash`, form `require`, symbol null |
| `import("./p/" + n)` | one edge to `unresolved:npm:import("./p/" + n)`, reason `dynamic` |

## Coverage

| Change | Rule |
|---|---|
| Analyzed extensions | `.py`, `.pyi`, `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, `.cjs`. A `.d.ts` file is `typescript` |
| New `detected_only` extensions | `.vue` → `vue`, `.svelte` → `svelte`, `.astro` → `astro` |
| Marker files | `jsconfig.json` → `javascript` is added. `package.json`, `tsconfig.json` and `jsconfig.json` stay `not_code` |
| `parse_error` on config files | Every loaded config (each `tsconfig.json` and `jsconfig.json`, and every file reached through `extends`) that cannot be read as a JSONC object gets this flag, whether or not any file uses it. Coverage keeps status `not_code`. A broken config counts as absent: files fall back to the next valid ancestor config, and a broken `extends` entry is skipped while the rest of the chain applies |
| `unreadable` on TS/JS | A TS/JS file that is not valid UTF-8 (a UTF-8 BOM is allowed and stripped) |
| Skipped folder names | Add `.next`, `.nuxt`, `.turbo`, `.svelte-kit`, `coverage`, `out`, `bower_components` to the 001 list |

## Resolution (TS/JS)

**Inputs.**

- `F`: every walked, non-skipped file path.
- `A`: the subset of `F` with status `analyzed`.
- The parsed configs (see research R4).
- `W`: workspace names, the `name` field of every `package.json` in `F` except `package.json` at the root.
  If two package files declare the same name, the name is still in `W`. A `package.json` that is not
  valid JSON, or has no string `name`, contributes nothing and gets no coverage flag: only its `name` is
  used, and nothing else depends on it.

**Trying a path.** `try(p)` returns the first of these that exists in `F`:

1. `p` itself;
2. `p` + each of `.ts`, `.tsx`, `.d.ts`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.json`;
3. if `p` ends with `.js`, `.jsx`, `.mjs` or `.cjs`: `p` with that suffix replaced by `.ts` / `.tsx`,
   `.tsx`, `.mts` or `.cts`, in that order;
4. `p/index` + each extension of step 2.

If the result is in `A`, the target is `file:<result>`. Otherwise it is `asset:<result>`. A written import
of an analyzed file in another language (for example `import "../backend/app.py"`) is therefore a normal
resolved `file:` edge: it is a fact in the code. Only heuristic cross-language links are out of scope.

**Normalizing a path.** Join the parts and resolve `.` and `..`. A path that goes above the root is
`outside`.

| Specifier | Result |
|---|---|
| Starts with `./` or `../`, or is `.` / `..` | `p` = normalize(importer folder + specifier). `outside`: reason `not_found`, and the reference is the specifier as written. Else `try(p)`, or reason `not_found` with the reference `p` |
| Starts with `/`, or is a URL (`<scheme>:` other than `node:`), or starts with `#` | Reason `not_found`, and the reference is the specifier as written |
| `node:<name>` | If the top segment of `<name>` is in the built-in list (prefix-only names included), the target is `ext:npm:<top>` with category `builtin`. Otherwise reason `not_found` |
| Bare, matching a `paths` pattern | Patterns are tried most specific first (an exact pattern first, then the longest prefix before `*`). For the first matching pattern, each target with `*` replaced is tried with `try` in listed order. The first hit wins. No hit: reason `not_found`, and the reference is the specifier as written. Patterns after the first match are not tried |
| Bare, with a `baseUrl` set | `try(normalize(baseUrl + specifier))`. A hit wins. No hit: continue below (unlike `paths`, `baseUrl` is only one of several places to look) |
| Bare, package name in `W` | Reason `workspace_package`, and the reference is the specifier as written |
| Bare, top segment in the built-in list and not prefix-only | `ext:npm:<top>`, category `builtin` |
| Bare, anything else | `ext:npm:<package name>`, category `third_party`. The package name is the first segment, or the first two for `@scope/name`. A specifier that is not a valid package name (empty segment, `@scope` without a name) gets reason `not_found` |
| Non-literal argument of `require` / `import()` | Reason `dynamic`, and the reference is the call text as written |

**Reference text for placeholders.** Whitespace in the reference is kept as written. A reference never
contains the ecosystem prefix; the node id adds it.

## Python changes

Only the serialization changes. Resolution rules, the module index and stdlib handling are unchanged.

- `ext:<name>` becomes `ext:python:<name>`, with `ecosystem: "python"`.
- `unresolved:<ref>` becomes `unresolved:python:<ref>`, with `ecosystem: "python"`.
- Edges get `form` and `type_only: false`, and `type` stays `imports`.
- Definitions and file nodes have no `exported_as` or `exports`.

## State

There is no persistent state. One run maps one folder to one `GraphDocument` v2.
