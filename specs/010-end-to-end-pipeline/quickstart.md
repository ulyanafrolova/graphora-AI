# Quickstart: End-to-End Pipeline (010)

Validation guide: proves the feature works end to end. Shapes are in [contracts/](contracts/); this file
only shows how to run them.

## Prerequisites

```bash
make db                                   # PostgreSQL 17 on 127.0.0.1:5432
cd backend && uv sync
export GRAPHORA_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora
export GRAPHORA_TEST_DATABASE_URL=postgresql://graphora:graphora@127.0.0.1:5432/graphora_test
```

## Automated checks

```bash
uv run pytest -m "not slow"               # everything, offline; GitHub is the in-process fake
uv run pytest tests/golden/test_pipeline_equivalence.py   # SC-001: HTTP == CLI --store, every fixture, 3 runs
make check                                # ruff + full suite, as in CI
```

## Manual run

```bash
uv run graphora serve                     # 127.0.0.1:8000, 1 worker, queue 20
```

1. **GitHub link (US1).** Start a job and poll it until `stage` is `done`:

   ```bash
   curl -s -X POST localhost:8000/api/v1/jobs -H 'Content-Type: application/json' \
        -d '{"github":"https://github.com/pallets/itsdangerous","ref":"main"}'
   curl -s localhost:8000/api/v1/jobs/<id>
   ```

   Expected: the first answer is `202` within a second with `stage` `queued` or later; polling shows the
   stages in order; `done` carries `repository`, `snapshot`, `action: "stored"` and counts.

2. **Read the result (FR-021).**

   ```bash
   curl -s "localhost:8000/api/v1/graph?repository=github.com/pallets/itsdangerous&snapshot=<sha>" > http.json
   uv run graphora analyze https://github.com/pallets/itsdangerous --ref <sha> > cli.json
   cmp http.json cli.json                    # identical
   uv run graphora mcp --repository github.com/pallets/itsdangerous --snapshot <sha>   # answers tools
   ```

3. **Reuse (US2).** Submit step 1 again: `done` with `action: "reused"` in under 2 seconds, nothing
   downloaded (no `fetching` stage seen).

4. **ZIP upload (US3).**

   ```bash
   (cd ../fixtures/repos/py-flat/repo && zip -qr /tmp/py-flat.zip .)
   curl -s -X POST "localhost:8000/api/v1/jobs/zip?name=py-flat.zip" \
        -H 'Content-Type: application/zip' --data-binary @/tmp/py-flat.zip
   ```

   Expected: `done` with `repository: "py-flat"` and the same `content:` snapshot as
   `graphora analyze /tmp/py-flat.zip`.

5. **Failures (US4).**
   - `{"github":"/etc"}` → `400` `not a GitHub repository link: /etc`, no job.
   - `{"github":"https://github.com/o/does-not-exist-xyz"}` → job `failed`, kind `remote`.
   - `{"github":"…","limits":{"max_files":1}}` → job `failed`, kind `limit`.
   - Upload with `?max_archive_bytes=10` → `413` `limit`.
   - Stop PostgreSQL (`make db-down`) and submit a new link → job `failed`, kind `store`.

6. **Cleanup (FR-018).** After every job, `ls $TMPDIR/graphora-jobs` shows only `.lock`. Kill the service
   with `kill -9` mid-analysis, start it again: the leftover job folder is gone.
