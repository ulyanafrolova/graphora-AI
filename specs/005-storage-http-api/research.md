# Research: Analysis Storage and HTTP API

Decisions for [plan.md](plan.md). Each entry: decision, rationale, alternatives.

## R1. Store engine: PostgreSQL through psycopg 3

- **Decision**: PostgreSQL 17, accessed with `psycopg` 3 (`psycopg[binary]`), plain SQL, no ORM. The
  connection string comes from `--database <url>` or the `GRAPHORA_DATABASE_URL` environment variable.
- **Rationale**: The constitution fixes PostgreSQL keyed by (repository, snapshot id). The store has three
  tables and a handful of queries, so an ORM would add a dependency without saving code. psycopg 3 binary
  wheels bundle libpq, so no system library is needed. libpq opens its own sockets, so the test suite's
  Python-level network block (`tests/conftest.py`) does not stop the local database connection and still
  catches any real network use.
- **Alternatives**: SQLAlchemy (more code paths than queries); asyncpg (async-only, the CLI is sync);
  SQLite (simpler tests, but a second engine to keep equal to production — a constitution deviation with no
  gain); files on disk (no transactions for FR-006/FR-009).

## R2. Schema creation: one idempotent SQL file, versioned

- **Decision**: `store/schema.sql` with `CREATE TABLE IF NOT EXISTS …` plus a `store_meta` row holding
  `store_version = 1`. `Store.open()` applies it in one transaction. If the database has a different
  `store_version`, opening fails with a "store unavailable: store version N, expected 1" error.
- **Rationale**: One version, three tables. A migration tool earns its place when there is a second
  version; until then a version check prevents silent mismatches.
- **Alternatives**: Alembic (needs SQLAlchemy); no version row (a future layout change would read old data
  wrongly).

## R3. What is stored for an analysis

- **Decision**: One `analyses` row: repository, snapshot, schema version, extractor versions (canonical
  JSON text), warnings (sorted JSON array text), graph bytes and their SHA-256. One `files` row per coverage
  entry: path, `has_text`, line count, SHA-256 and size of the analyzed bytes. File bytes live once in a
  `blobs` table keyed by SHA-256 and shared between snapshots.
- **Rationale**: The graph is kept as the exact bytes the serializer produced (FR-003, FR-013); re-encoding
  JSON from `jsonb` would change key order and spacing. Deduplication by hash keeps repeated snapshots of the
  same repository small, since most files do not change between commits. No timestamps are stored, so
  nothing time-dependent can leak into responses (FR-016).
- **Alternatives**: `jsonb` graph (loses byte identity); one row per file with inline bytes (duplicates every
  unchanged file per commit); storing only analyzed files (the viewer could not show `package.json` or
  `tsconfig.json`, see spec Assumptions).

## R4. Stored bytes are the analyzed bytes

- **Decision**: Split `graph.build.build()` into `graph.build.analyze()` returning
  `Analysis(doc, warnings, contents)`, where `contents` maps each readable walked file to the exact bytes the
  analysis read. `build()` stays as a thin wrapper with the same signature and result. The store saves
  `contents`, never re-reading the folder.
- **Rationale**: Re-reading a local folder after analysis races with edits: the stored text could differ from
  the text the line numbers and snippet hashes were computed from, breaking provenance (Principle III).
  `build()` already holds these bytes in memory.
- **Alternatives**: Re-read inside the `fetch_snapshot` block (safe for archives, unsafe for local folders);
  hash check after re-read (detects the race but cannot recover).

## R5. Text, encoding and line numbering

- **Decision**: A file has text when the adapter's decoding rule succeeds: PEP 263 detection for `.py`
  files (the same `_decode` the Python adapter uses), strict UTF-8 for every other file, and in both cases no
  NUL byte. Lines end at `\n`, `\r\n` or a lone `\r`, matching `adapters/position.py`, so line N in the API is
  line N in every edge. A UTF-8 BOM is kept in the stored bytes and removed from the first served line. Files
  flagged `unreadable` have no stored bytes and are `has_text = false`.
- **Rationale**: The provenance card and the future claim verifier compare an edge's `line` against served
  lines; any difference in line splitting would make correct edges look wrong.
- **Alternatives**: Universal-newline decoding of all files as UTF-8 (wrong for Latin-1 Python files with a
  coding cookie); serving raw bytes (the client would have to repeat the rules).

## R6. Reuse rule and GitHub short-circuit

- **Decision**: An analysis is reusable when its `schema_version` equals `SCHEMA_VERSION` and its extractor
  map equals `graph.build.current_extractors()` (a new function returning the map `build()` writes). For
  GitHub sources the CLI resolves the ref first (`github.resolve_sha`), checks the store, and only on a miss
  calls `fetch_snapshot(source, limits, deadline, sha=sha)`. The new optional `sha` parameter skips the
  second resolve, keeping "at most one request to api.github.com" true. For local folders and ZIPs the
  snapshot id exists only after `analyze()`, so reuse means "do not write again".
- **Rationale**: FR-007, FR-008 and SC-002 (no download for a stored commit). Comparing the full extractor
  map catches any resolver or table bump.
- **Alternatives**: Compare only `schema_version` (misses resolver fixes); resolve the ref twice (two API
  calls against a 60/hour anonymous limit). The `sha` parameter touches `ingest/fetch.py`, owned by Anna:
  the PR requests her review (team-workflow.md).

## R7. Atomic, concurrent-safe writes

- **Decision**: One transaction per analysis: take `pg_advisory_xact_lock` on a 64-bit hash of
  `repository + "\0" + snapshot`, re-check reusability, delete the old row (files cascade) if stale, insert
  blobs with `ON CONFLICT DO NOTHING`, insert the analysis and its files, commit. Readers use plain
  `READ COMMITTED` reads, which see either the old or the new committed state.
- **Rationale**: FR-006 and FR-009 and the "CLI writes while API reads" edge case, with no application-level
  locking. The lock only serializes writers of the same pair.
- **Alternatives**: `SERIALIZABLE` with retries (more code for the same result); unique constraint alone
  (second writer fails instead of reusing).

## R8. Validate before storing

- **Decision**: The graph document is validated against `schema/graph.schema.json` before the write
  transaction; `jsonschema` moves from the dev group to runtime dependencies. A failure aborts with an
  internal error and stores nothing.
- **Rationale**: Spec edge case; the store is the boundary every later consumer trusts.
- **Alternatives**: Trust the serializer (a bug would be stored and served for ever, since stored data is
  immutable).

## R9. HTTP framework and server

- **Decision**: FastAPI with uvicorn; `graphora serve` starts uvicorn bound to `127.0.0.1:8000` by default
  (`--host`, `--port` override). Tests use FastAPI's `TestClient` (in-process, no socket).
- **Rationale**: Constitution technical constraints name FastAPI. In-process tests keep the offline suite.
- **Alternatives**: Starlette alone (FastAPI's validation and OpenAPI help the frontend team for little cost).

## R10. URL shape: query parameters for repository and snapshot

- **Decision**: `GET /api/v1/repositories`, `GET /api/v1/graph?repository=&snapshot=`,
  `GET /api/v1/file?repository=&snapshot=&path=[&start=&end=]`.
- **Rationale**: Repository names contain `/` (`github.com/o/r`) and paths contain `/`; putting both into path
  segments makes routes ambiguous. Query parameters are unambiguous; clients must percent-encode, notably `+`
  in `<sha>+dirty:<hash>` snapshots (`%2B`). A `/api/v1` prefix leaves room for 007 and later slices.
- **Alternatives**: `/repos/{id}` with a surrogate id (needs a lookup step and an id that is not
  content-derived); `{repository:path}` converters (ambiguous with a trailing `/graph`).

## R11. Deterministic responses and errors

- **Decision**: The graph endpoint returns the stored bytes as `application/json` unchanged. Other bodies are
  encoded with `json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))`. Errors are
  `{"error": {"kind": ..., "message": ...}}` with kinds `bad_request` (400), `not_found` (404),
  `store_unavailable` (503). FastAPI's default 422 validation response is replaced by `bad_request` with a
  message naming the parameter. Unhandled exceptions return `internal` (500) with a fixed message; details go
  to the server log only.
- **Rationale**: FR-016 and FR-017. FastAPI's default validation body contains the input echo and an error
  URL; a fixed shape is easier for the frontend and keeps paths out of responses.

## R12. Tests need a real PostgreSQL

- **Decision**: Tests that touch the store are marked `db` and use `GRAPHORA_TEST_DATABASE_URL`. A
  `docker-compose.yml` at the repository root starts `postgres:17` on `127.0.0.1:5432`; `make db` runs it.
  CI adds a `postgres:17` service container and sets the variable. When the variable is missing, `db` tests
  fail with a message saying how to start the database (`make db`) or deselect them (`-m "not db"`); they do
  not skip silently. Each test gets an empty store by truncating the three tables.
- **Rationale**: Constitution VIII: a feature is done when its tests pass, so silent skips would hide a
  broken store. Running the same engine as production avoids SQLite/PostgreSQL differences.
- **Alternatives**: `pgserver` / embedded binaries (fewer setup steps, but an extra binary dependency with
  uncertain platform support); skipping without a database (green CI with an untested store).

## R13. CLI changes

- **Decision**: `graphora analyze … --store [--database URL]` and a new `graphora serve [--database URL]
  [--host] [--port]`. With `--store`, stdout/`--out` output is unchanged (on reuse, the stored bytes, which
  are identical by R6), and one extra stderr line reports `stored <repository> <snapshot>` or
  `reused <repository> <snapshot>`. A new exit code 6 means the store is unavailable or has the wrong
  version. Without `--store`, nothing connects to a database.
- **Rationale**: FR-011, keeps every existing test and message unchanged (SC-007).
