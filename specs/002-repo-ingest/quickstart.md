# Quickstart: validating 002 repo-ingest

How to check that the feature works end to end. Behaviour is defined in [spec.md](spec.md) and
[contracts/cli.md](contracts/cli.md); this guide only lists what to run and what to expect.

## Prerequisites

```
cd backend && uv sync
```

No GitHub account or token. Steps 1–4 need no network.

## 1. Full suite, offline

```
uv run pytest                      # network calls fail the test by design (research R10)
```

Expect: all tests pass, including every test that existed before 002, with no edits to them or to any
`expected.json` (SC-006, FR-015).

## 2. Local folder unchanged

```
git switch -q main && uv run graphora analyze ../fixtures/repos/ts-app/repo --out /tmp/before.json
git switch -q 002-repo-ingest && uv run graphora analyze ../fixtures/repos/ts-app/repo --out /tmp/after.json
cmp /tmp/before.json /tmp/after.json && echo identical
```

Expect: `identical` (US4).

## 3. ZIP of a fixture

```
(cd ../fixtures/repos/py-flat && zip -qry /tmp/py-flat.zip repo)
uv run graphora analyze /tmp/py-flat.zip --out /tmp/zip.json
uv run graphora analyze ../fixtures/repos/py-flat/repo --out /tmp/dir.json
diff <(jq 'del(.snapshot) | .edges[] |= del(.snapshot)' /tmp/zip.json) \
     <(jq 'del(.snapshot) | .edges[] |= del(.snapshot)' /tmp/dir.json) && echo same graph
```

Expect: `same graph`; the ZIP's snapshot is `content:<hash>`; running it twice gives identical bytes
(US2).

## 4. Hostile and broken inputs

```
uv run pytest tests/unit/test_archive.py tests/integration/test_ingest_cleanup.py -v
uv run graphora analyze ./README.md; echo $?          # 2, "not a directory or ZIP archive"
printf 'PK\003\004garbage' > /tmp/bad.zip
uv run graphora analyze /tmp/bad.zip; echo $?         # 4, invalid ZIP archive
ls "${TMPDIR:-/tmp}" | grep '^graphora-' || echo "no temp left"
```

Expect: every hostile case passes (SC-003, SC-005) and `no temp left` (SC-004).

## 5. Real GitHub (manual, needs network)

```
uv run graphora analyze https://github.com/<owner>/<small-public-repo> --out /tmp/gh.json
jq -r .snapshot /tmp/gh.json                                    # 40 hex characters
uv run graphora analyze https://github.com/<owner>/<repo> --ref <tag> --out /tmp/gh2.json
uv run graphora analyze https://github.com/<owner>/does-not-exist; echo $?   # 2
uv run graphora analyze https://github.com/<owner>/<repo> --max-seconds 0.5; echo $?  # 3
```

Expect: SHA snapshots; repeating a run on an unmoved ref gives identical bytes (US1); the clone check
below matches.

```
git clone -q https://github.com/<owner>/<repo> /tmp/clone && git -C /tmp/clone checkout -q <sha>
uv run graphora analyze /tmp/clone --out /tmp/clone.json && cmp /tmp/gh.json /tmp/clone.json
```

Expect identical bytes unless the repository uses `export-ignore`/`export-subst` (research R12).
