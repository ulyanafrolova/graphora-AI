# Python Contract: the fetch step (`graphora.ingest`)

The CLI uses this today. Features 005 (HTTP upload, API) and 007 (pipeline) will call the same functions,
so they are a contract. Types are described in [data-model.md](../data-model.md).

```python
from graphora.ingest.source import parse_source          # str, ref -> Source
from graphora.ingest.fetch import fetch_snapshot, IngestLimits, FetchedSnapshot
from graphora.ingest.errors import BadInput, UnsafeArchive, InvalidArchive, RemoteError
from graphora.ingest.walk import Deadline, LimitExceeded
from graphora.graph.build import build

source = parse_source(argument, ref=None)                # raises BadInput
deadline = Deadline(300)
with fetch_snapshot(source, IngestLimits(), deadline) as fetched:   # raises any error above
    doc, warnings = build(fetched.root, max_files, max_bytes, deadline, snapshot=fetched.snapshot)
    doc = with_skipped(doc, fetched.skipped)              # from graphora.ingest.fetch
    data = dumps(doc)
# temp folder is gone here, whatever happened inside the block
```

## Guarantees

- `parse_source` does no I/O except `stat` and reading the first 4 bytes of a file.
- `fetch_snapshot` makes at most one request to `api.github.com` and one to `codeload.github.com`, sends no
  credentials, never runs a subprocess, and never writes outside its own temp folder.
- `fetched.root` contains only regular files (mode `0o644`), folders and empty markers; never a link.
- On leaving the `with` block, normally or by any exception including `KeyboardInterrupt`, the temp folder
  is removed. A `LocalSource` creates no temp folder and its folder is never written to.
- `with_skipped(doc, extra)` returns a copy of `doc` whose `skipped` is `doc.skipped + extra`, sorted by
  path. With `extra == ()` it returns `doc` unchanged.
- The order and content of `fetched.skipped` do not depend on archive order (sorted by path).

## `build()` signature change

```python
def build(root: Path, max_files: int, max_bytes: int, deadline: Deadline,
          snapshot: str | None = None) -> tuple[GraphDocument, tuple[str, ...]]
```

`snapshot=None` keeps the current behaviour exactly.
