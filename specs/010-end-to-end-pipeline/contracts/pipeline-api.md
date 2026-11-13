# Python Contract: `graphora.pipeline` (new in 010)

Used by `graphora analyze --store`, the job runner, and later by agents (012) and the HTTP bridge (015).

## `run_pipeline`

```python
def run_pipeline(
    source: GitHubSource | ZipSource | LocalSource,
    limits: PipelineLimits,
    store: Store,
    deadline: Deadline,
    on_stage: Callable[[Stage], None] = lambda stage: None,
    workdir: Path | None = None,
) -> PipelineResult
```

- Runs: resolve the ref (GitHub only) → `store.find_reusable` → `fetch_snapshot(..., sha=…, workdir=workdir)`
  → `analyze` → `with_skipped` → `store.put`. Exactly the steps of 005's `cli._analyze_and_store`.
- Calls `on_stage("resolving" | "fetching" | "analyzing" | "storing")` before each step, in order; never
  calls it for `done`/`failed` (the caller sets those).
- Raises the existing exceptions unchanged: `BadInput`, `RemoteError`, `LimitExceeded`, `UnsafeArchive`,
  `InvalidArchive`, `StoreUnavailable`, `InvalidAnalysis`, plus whatever `deadline.check()` raises.
- Leaves nothing in `workdir` (or the system temp) when it returns or raises.

```python
@dataclass(frozen=True)
class PipelineLimits:          # the six ingest/analysis limits
    max_files: int; max_bytes: int; max_seconds: float
    max_archive_bytes: int; max_extract_bytes: int; max_entries: int

@dataclass(frozen=True)
class PipelineResult:
    analysis: StoredAnalysis   # repository, snapshot, graph bytes, warnings
    action: Literal["stored", "replaced", "reused"]
    fetched: str | None        # "fetched … at …" / "extracted …" info for the CLI; None on a GitHub reuse

Stage = Literal["resolving", "fetching", "analyzing", "storing"]
```

## `graphora.pipeline.messages`

```python
def limit_message(exc: LimitExceeded, style: Literal["cli", "api"]) -> str
```

The 005 templates, with `--max-files` for `cli` and `max_files` for `api` (research R11).

## `graphora.pipeline.jobs`

```python
class JobRunner:
    def __init__(self, database_url: str, limits: PipelineLimits, workers: int = 1,
                 queue_size: int = 20, work_dir: Path | None = None,
                 pipeline: Callable[..., PipelineResult] = run_pipeline) -> None
    def start(self) -> None          # lock and clean work_dir, start worker threads
    def stop(self) -> None           # R7
    def submit_github(self, source: GitHubSource, limits: PipelineLimits) -> JobStatus
    def submit_zip(self, name: str, upload: Path, limits: PipelineLimits) -> JobStatus
    def new_upload(self) -> Path     # a fresh file path inside work_dir for a streaming upload
    def status(self, job_id: str) -> JobStatus | None
```

- `submit_*` raise `QueueFull` when the queue holds `queue_size` jobs.
- `JobStatus.to_json() -> bytes` gives the body in [http-api.md](http-api.md).
- `pipeline` is injectable for unit tests without a database.

## `graphora.ingest.fetch` (one optional parameter)

```python
def fetch_snapshot(source, limits, deadline, sha=None, workdir: Path | None = None)
```

`workdir` is passed to `tempfile.TemporaryDirectory(dir=workdir)`. `None` keeps the 002 behaviour.
