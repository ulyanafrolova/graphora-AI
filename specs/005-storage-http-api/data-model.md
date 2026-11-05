# Data Model: Analysis Storage and HTTP API

The graph document and `schema/graph.schema.json` do **not** change (schema v2 stays). This file describes
the PostgreSQL store (`backend/src/graphora/store/`) and the in-memory types around it. Research references:
[research.md](research.md).

## In memory

### Analysis (`graph.build.analyze()` result, R4)

| Field | Type | Meaning |
|---|---|---|
| `doc` | `GraphDocument` | as today |
| `warnings` | `tuple[str, ...]` | as today |
| `contents` | `Mapping[str, bytes]` | exact bytes read for each readable walked file, keyed by coverage path |

`build(...)` returns `(analysis.doc, analysis.warnings)` exactly as before.

### StoredAnalysis (returned by `Store.get_analysis`)

| Field | Type |
|---|---|
| `repository` | `str` |
| `snapshot` | `str` |
| `schema_version` | `int` |
| `extractors` | `dict[str, str]` |
| `warnings` | `tuple[str, ...]` |
| `graph` | `bytes` (exact serialized document) |

### FileText (returned by `Store.get_file`)

| Field | Type | Meaning |
|---|---|---|
| `path` | `str` | exact coverage path |
| `has_text` | `bool` | R5 rule |
| `line_count` | `int` | 0 when `has_text` is false; a file ending with a newline does not count an extra empty line |
| `lines` | `tuple[str, ...]` | requested lines without line endings, BOM removed from line 1 |
| `start`, `end` | `int` | 1-based inclusive range actually returned |

## PostgreSQL tables (`store/schema.sql`, store version 1)

```text
store_meta
  key    text PRIMARY KEY            -- 'store_version'
  value  text NOT NULL               -- '1'

analyses
  repository      text   NOT NULL
  snapshot        text   NOT NULL    CHECK matches the schema snapshot pattern
  schema_version  int    NOT NULL
  extractors      text   NOT NULL    -- canonical JSON object, sorted keys
  warnings        text   NOT NULL    -- canonical JSON array, sorted
  graph           bytea  NOT NULL
  graph_sha256    text   NOT NULL
  PRIMARY KEY (repository, snapshot)

blobs
  sha256   text  PRIMARY KEY         -- hex of content
  content  bytea NOT NULL

files
  repository  text    NOT NULL
  snapshot    text    NOT NULL
  path        text    NOT NULL
  has_text    boolean NOT NULL
  line_count  int     NOT NULL
  size        bigint  NULL           -- NULL when unreadable
  sha256      text    NULL REFERENCES blobs   -- NULL when unreadable or has_text = false
  PRIMARY KEY (repository, snapshot, path)
  FOREIGN KEY (repository, snapshot) REFERENCES analyses ON DELETE CASCADE
```

No timestamps, sequences or random ids: every stored value is derived from the analysis (Principle II).

## Rules

- **Repository name** (FR-002): taken from `FetchedSnapshot.repository` (002 data-model) — never from user
  input in the API. Non-empty, at most 300 characters.
- **One analysis per pair** (FR-001): primary key on `(repository, snapshot)`.
- **Files set** (FR-004): exactly the paths in `coverage.files` of the stored graph, no more, no less.
  Skipped entries and symlinks are never rows.
- **Text content**: bytes are stored only when `has_text` is true (R3, R5). Binary or undecodable files keep
  `size` and `has_text = false` so the API can say "no text content".
- **Immutability** (FR-005): the store has no update operation; replacement is delete-then-insert in one
  transaction (R7). Orphaned blobs are allowed and never served.
- **Reusable** (FR-007, R6): `schema_version == SCHEMA_VERSION and extractors == current_extractors()`.

## State transitions of one (repository, snapshot) pair

```text
absent ──store──▶ stored(v)                    v = (schema_version, extractors)
stored(v) ──store, v == current──▶ stored(v)   reused; no write
stored(v) ──store, v != current──▶ stored(current)   replaced atomically
any ──failed or interrupted write──▶ unchanged
```
