# Quickstart: validate the Python Import Graph CLI

## Prerequisites

- `uv` 0.12 or newer. It installs Python 3.12+ itself if needed.
- A clone of this repository on branch `001-python-graph-cli`.

## Setup

```
cd backend
uv sync
```

## 1. Golden tests (US1 and US2)

```
uv run pytest tests/golden -q
```

**Expected result:** all tests pass, one for each fixture in `fixtures/repos/*/`. Each test checks that
the projected output equals `expected.json` exactly, with no missing and no extra nodes, edges, coverage
entries or skipped paths. The comparison format is described in [research.md § R10](research.md).

## 2. Determinism (US3)

```
uv run pytest tests/golden -q -k determinism
```

**Expected result:** for each fixture, 10 runs give byte-identical output, and so does a run on a copy of
the fixture in a temp folder with a different absolute path. You can also check by hand:

```
uv run graphora analyze ../fixtures/repos/py-flat/repo --out /tmp/a.json
cp -R ../fixtures/repos/py-flat/repo /tmp/flatcopy
uv run graphora analyze /tmp/flatcopy --out /tmp/b.json
cmp /tmp/a.json /tmp/b.json && echo identical
```

## 3. Schema validation

```
uv run pytest tests/contract -q
```

**Expected result:** every fixture's output validates against `schema/graph.schema.json`. Hand-made
invalid documents are rejected: an edge without `snippet_hash`, an unresolved edge without `reason`, and a
resolved edge pointing to an `unresolved:` node.

## 4. Snapshot ids on a git repository

```
tmp=$(mktemp -d) && cp -R ../fixtures/repos/py-flat/repo/. "$tmp" && cd "$tmp"
git init -q && git add -A && git commit -qm init
uv run --project <repo>/backend graphora analyze . | grep -m1 '"snapshot"'   # 40-hex SHA
echo "# x" >> $(ls *.py | head -1)
uv run --project <repo>/backend graphora analyze . | grep -m1 '"snapshot"'   # <sha>+dirty:<16hex>
```

The same check is automated in `tests/integration/test_snapshot.py`, which builds the repository in a temp
folder.

## 5. Error paths

```
uv run graphora analyze /does/not/exist; echo $?                                          # 2
uv run graphora analyze ../fixtures/repos/py-flat/repo --max-files 1 --out /tmp/x.json; echo $?  # 3, /tmp/x.json not created
uv run graphora analyze ../fixtures/repos/py-flat/repo --out ../fixtures/repos/py-flat/repo/g.json; echo $?  # 2
```

## 6. Safety smoke test

The fixture `py-dynamic` contains a module that writes a marker file when it is imported.
`tests/integration/test_safety.py` copies the fixture to a temp folder and runs `git init` there. It then
adds a `.gitattributes` file and a `filter.evil.clean` setting in `.git/config`, both of which would write
a marker file if `git` ran a filter. After analysis, the test asserts that neither marker file exists.
