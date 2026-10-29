# Quickstart: validate TS/JS analysis and schema v2

This guide proves the feature end to end. The rules it checks are in [data-model.md](data-model.md) and
[contracts/](contracts/), and the fixtures' `expected.json` files are the ground truth.

## Prerequisites

- `uv` installed, and the repository checked out on `003-ts-js-analysis`.
- No Node.js is needed. If one is installed, it must not be used: the analysis never calls it.
- `jq` is optional, for the manual checks.

```
cd backend && uv sync
```

## 1. All tests

```
uv run pytest -m "not slow"     # golden, contract, unit and integration tests
uv run pytest -m slow           # performance (SC-005): about 1,000 TS/JS files in under 30 s
```

Expected: all pass. The golden tests run over every folder in `fixtures/repos/` that has an
`expected.json`: the three Python fixtures, now in v2 form, and the four new ones.

## 2. TS/JS resolution (User Story 1)

```
uv run graphora analyze ../fixtures/repos/ts-app/repo --out /tmp/ts-app.json
jq '.schema_version' /tmp/ts-app.json                                   # 2
jq '.edges[] | select(.source=="file:src/main.ts") | {target, symbol, line, confidence}' /tmp/ts-app.json
```

Check against `fixtures/repos/ts-app/expected.json`. These must hold:

- the `@app/*` alias resolves into `src/`;
- the `./util.js` specifier resolves to `util.ts`;
- the folder import resolves to `index.ts`;
- `node:fs` and `fs` share the node `ext:npm:fs`;
- the CSS import targets an `asset:` node;
- the missing alias `@app/missing` falls through to the npm package node `ext:npm:@app/missing`, as in TypeScript.

## 3. CommonJS and dynamic imports

```
uv run graphora analyze ../fixtures/repos/js-commonjs/repo | jq '[.edges[] | select(.form!="static") | {source, target, form, confidence, reason}]'
```

Expected:

- `require("lodash")` resolves to `ext:npm:lodash` with form `require`;
- `require(name)` and `` import(`./p/${n}`) `` are `unresolved` with reason `dynamic`;
- a template literal without substitutions resolves.

## 4. Barrels and exports (User Story 2)

```
uv run graphora analyze ../fixtures/repos/ts-monorepo/repo --out /tmp/mono.json
jq '.edges[] | select(.type=="reexports") | {source, target, symbol, alias}' /tmp/mono.json
jq '.nodes[] | select(.id=="file:packages/ui/src/log.ts") | .definitions' /tmp/mono.json
```

Expected:

- every `export … from` statement in the barrel is a `reexports` edge;
- `Log` has `exported_as: ["Log"]` (the barrel re-exports it as `Logger`), and `format` has `["fmt2"]`
  (a local `export { format as fmt2 }`). A non-exported definition with `[]` is `track` in
  `fixtures/repos/ts-app/repo/src/components/Button.tsx`;
- the app's import of `@acme/ui` is `unresolved` with reason `workspace_package`;
- no edge goes from the app to `packages/ui/src/log.ts` directly (FR-007b).

Manual SC-006 check: starting from the app's `Logger` import, follow `imports` → `reexports` → the
definition using only the JSON. It should take under a minute.

## 5. Mixed repository and ecosystems (User Story 3)

```
uv run graphora analyze ../fixtures/repos/mixed-fullstack/repo | jq '[.nodes[] | select(.kind=="external") | .id]'
```

Expected: both `ext:python:yaml` and `ext:npm:yaml` are present, and both languages are `analyzed` in
coverage.

## 6. Python fixtures unchanged apart from v2 (SC-003)

```
uv run pytest tests/golden -k py
```

The v1-equivalence test maps the v2 ids back to the v1 form and compares the nodes and edges with the
frozen v1 files in `backend/tests/golden/v1/` (research R9).

## 7. Determinism and safety

```
uv run pytest tests/golden -k determinism
uv run pytest tests/integration/test_safety.py tests/integration/test_safety_ts.py
```

Expected:

- 10 runs and a copied path give byte-identical output for every fixture;
- the safety test confirms that no process is spawned and nothing outside `<dir>` is read, including a
  `tsconfig` `extends` that points outside the root.
