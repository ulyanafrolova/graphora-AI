# Python Contract: the store (`graphora.store`)

Used by the CLI and the HTTP API in 005, and by the MCP server (006), the pipeline (007) and the claim
verifier (008) later. They call these functions and never write SQL themselves.

```python
from graphora.store import Store, StoreUnavailable, StoreResult
from graphora.graph.build import analyze, current_extractors

store = Store.open(url)                       # applies schema.sql; raises StoreUnavailable
store.find_reusable(repository, snapshot)     # -> StoredAnalysis | None   (R6 rule)
result = store.put(repository, analysis)      # -> StoreResult("stored" | "replaced" | "reused", StoredAnalysis)
store.list_repositories()                     # -> tuple[tuple[str, tuple[str, ...]], ...], sorted
store.get_analysis(repository, snapshot)      # -> StoredAnalysis | None
store.get_file(repository, snapshot, path, start=None, end=None)
                                              # -> FileText | None; raises ValueError on a bad range
store.close()
```

Types: [data-model.md](../data-model.md).

## Guarantees

- `put` validates `analysis.doc` against `schema/graph.schema.json`, serializes it with `graph.serialize.dumps`,
  and writes the analysis, its files and blobs in one transaction under an advisory lock on the pair (R7).
  Reusable → `"reused"`, nothing written. Stale → `"replaced"`. Absent → `"stored"`.
- `put` raises (and writes nothing) if the files in `analysis.contents` plus unreadable coverage entries do
  not match `coverage.files` exactly.
- Reads see only committed analyses; a concurrent `put` is seen entirely or not at all.
- No function reads the file system, runs a subprocess or opens a network connection other than the
  database connection.
- Every returned sequence is sorted; no function returns timestamps or values that differ between calls on
  unchanged data.
- Any database connection failure is raised as `StoreUnavailable(reason)`; `reason` has no password.

## Changes to existing modules

```python
# graphora.graph.build (owner: Ulyana)
def analyze(root, max_files, max_bytes, deadline, snapshot=None) -> Analysis
def build(root, max_files, max_bytes, deadline, snapshot=None) -> tuple[GraphDocument, tuple[str, ...]]  # unchanged
def current_extractors() -> dict[str, str]    # the map build() writes into `extractors`

# graphora.ingest.fetch (owner: Anna — PR requests her review)
def fetch_snapshot(source, limits, deadline, sha: str | None = None)
# sha given for a GitHubSource: skip resolve_sha and download that commit (40 lower-case hex, else ValueError).
# sha given for any other source: ValueError.
# sha=None keeps the 002 behaviour exactly.
```
