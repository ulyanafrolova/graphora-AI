"""`graphora analyze` and `graphora serve` (contracts/cli.md; 005: specs/005-storage-http-api/contracts/cli.md)."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import signal
import sys
import tempfile
import threading
from pathlib import Path

from graphora.graph.build import build
from graphora.graph.serialize import dumps
from graphora.ingest.errors import BadInput, InvalidArchive, RemoteError, UnsafeArchive
from graphora.ingest.fetch import IngestLimits, fetch_snapshot, with_skipped
from graphora.ingest.source import GitHubSource, LocalSource, Source, ZipSource, parse_source
from graphora.ingest.walk import Deadline, LimitExceeded

EXIT_OK, EXIT_USAGE, EXIT_LIMIT = 0, 2, 3
EXIT_ARCHIVE, EXIT_REMOTE, EXIT_STORE, EXIT_INTERRUPTED = 4, 5, 6, 130

_LIMIT_MESSAGES = {
    "files": "file limit exceeded: at least {observed} files > --max-files {value}",
    "bytes": "size limit exceeded: at least {observed} bytes > --max-bytes {value}",
    "seconds": "time limit exceeded: {observed}s > --max-seconds {value}",
    "archive_bytes": "archive size limit exceeded: at least {observed} bytes > --max-archive-bytes {value}",
    "extract_bytes": "extracted size limit exceeded: at least {observed} bytes > --max-extract-bytes {value}",
    "entries": "entry limit exceeded: at least {observed} entries > --max-entries {value}",
}


def _log(level: str, message: str) -> None:
    print(f"graphora: {level}: {message}", file=sys.stderr)


class _StoreFailed(Exception):
    """A store error, raised by the `--store` path so that `psycopg` is imported only when it is used."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclasses.dataclass(frozen=True)
class _Report:
    """What `analyze` prints to stderr after the graph: info lines, warnings and the summary."""

    info: tuple[str, ...]
    warnings: tuple[str, ...]
    files: int
    edges: int
    unresolved: int
    snapshot: str


def _report_from_bytes(info: tuple[str, ...], warnings: tuple[str, ...], data: bytes) -> _Report:
    doc = json.loads(data)
    files = sum(1 for f in doc["coverage"]["files"] if f["status"] == "analyzed")
    unresolved = sum(1 for e in doc["edges"] if e["confidence"] == "unresolved")
    return _Report(info, warnings, files, len(doc["edges"]), unresolved, doc["snapshot"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphora")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="build the import graph of a folder, GitHub repository or ZIP")
    analyze.add_argument("dir", metavar="source", help="a local folder, a GitHub link or a ZIP file")
    analyze.add_argument("--ref")
    analyze.add_argument("--out")
    analyze.add_argument("--max-files", type=int, default=5000)
    analyze.add_argument("--max-bytes", type=int, default=50 * 1024 * 1024)
    analyze.add_argument("--max-seconds", type=float, default=300)
    analyze.add_argument("--max-archive-bytes", type=int, default=IngestLimits.max_archive_bytes)
    analyze.add_argument("--max-extract-bytes", type=int, default=IngestLimits.max_extract_bytes)
    analyze.add_argument("--max-entries", type=int, default=IngestLimits.max_entries)
    analyze.add_argument("--store", action="store_true", help="save the analysis in the store, or reuse a stored one")
    analyze.add_argument("--database", help="PostgreSQL URL (default: $GRAPHORA_DATABASE_URL); only with --store")
    serve = commands.add_parser("serve", help="serve stored analyses over a read-only HTTP API")
    serve.add_argument("--database", help="PostgreSQL URL (default: $GRAPHORA_DATABASE_URL)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def _database_url(given: str | None) -> str | None:
    return given or os.environ.get("GRAPHORA_DATABASE_URL") or None


def _write_atomic(out: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=f".{out.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, out)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _raise_interrupt(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    if args.command == "serve":
        return _serve(args)

    # SIGTERM must also unwind through fetch_snapshot so the temp folder is removed (research § R11).
    in_main_thread = threading.current_thread() is threading.main_thread()
    previous = signal.signal(signal.SIGTERM, _raise_interrupt) if in_main_thread else None
    try:
        return _analyze(args)
    finally:
        if in_main_thread:
            signal.signal(signal.SIGTERM, previous)


def _serve(args: argparse.Namespace) -> int:
    from graphora.store import Store, StoreUnavailable

    url = _database_url(args.database)
    try:
        if url is None:
            raise StoreUnavailable("no database URL: use --database or GRAPHORA_DATABASE_URL")
        store = Store.open(url)
    except StoreUnavailable as exc:
        _log("error", f"store unavailable: {exc.reason}")
        return EXIT_STORE
    try:
        import uvicorn

        from graphora.api import create_app

        uvicorn.run(create_app(store), host=args.host, port=args.port)
    finally:
        store.close()
    return EXIT_OK


def _analyze_and_store(
    args: argparse.Namespace, source: Source, limits: IngestLimits, deadline: Deadline
) -> tuple[bytes, _Report]:
    """The `--store` path (005 contracts/cli.md, research § R6). Nothing is printed here."""
    from graphora.graph.build import analyze
    from graphora.ingest import github
    from graphora.store import InvalidAnalysis, Store, StoreUnavailable

    url = _database_url(args.database)
    try:
        if url is None:
            raise StoreUnavailable("no database URL: use --database or GRAPHORA_DATABASE_URL")
        store = Store.open(url)
    except StoreUnavailable as exc:
        raise _StoreFailed(EXIT_STORE, f"store unavailable: {exc.reason}") from None
    try:
        sha = None
        if isinstance(source, GitHubSource):
            sha = github.resolve_sha(source, deadline)
            repository = f"github.com/{source.owner}/{source.repo}"
            stored = store.find_reusable(repository, sha)
            if stored is not None:  # nothing to download: no `fetched` line (contracts/cli.md)
                info = (f"reused {repository} {sha}",)
                return stored.graph, _report_from_bytes(info, stored.warnings, stored.graph)
        with fetch_snapshot(source, limits, deadline, sha=sha) as fetched:
            result = analyze(fetched.root, args.max_files, args.max_bytes, deadline, snapshot=fetched.snapshot)
            result = dataclasses.replace(result, doc=with_skipped(result.doc, fetched.skipped))
            stored_result = store.put(fetched.repository, result)
        info = ()
        if isinstance(source, GitHubSource):
            info = (f"fetched {fetched.repository} at {fetched.snapshot}",)
        elif isinstance(source, ZipSource):
            info = (f"extracted {source.path.name}",)
        saved = stored_result.analysis
        info += (f"{stored_result.action} {saved.repository} {saved.snapshot}",)
        return saved.graph, _report_from_bytes(info, saved.warnings, saved.graph)
    except StoreUnavailable as exc:
        raise _StoreFailed(EXIT_STORE, f"store unavailable: {exc.reason}") from None
    except InvalidAnalysis as exc:
        raise _StoreFailed(EXIT_USAGE, f"cannot store the analysis: {exc}") from None
    finally:
        store.close()


def _analyze(args: argparse.Namespace) -> int:
    if args.database is not None and not args.store:
        _log("error", "--database requires --store")
        return EXIT_USAGE
    deadline = Deadline(args.max_seconds)
    limits = IngestLimits(args.max_archive_bytes, args.max_extract_bytes, args.max_entries)
    try:
        source = parse_source(args.dir, args.ref)
        out = Path(args.out).resolve() if args.out else None
        if isinstance(source, LocalSource) and out is not None:
            root = source.path.resolve()
            if out == root or root in out.parents:
                _log("error", "--out must not be inside the analyzed folder")
                return EXIT_USAGE
        if args.store:
            data, report = _analyze_and_store(args, source, limits, deadline)
        else:
            with fetch_snapshot(source, limits, deadline) as fetched:
                doc, warnings = build(fetched.root, args.max_files, args.max_bytes, deadline, snapshot=fetched.snapshot)
                doc = with_skipped(doc, fetched.skipped)
                data = dumps(doc)
            info: tuple[str, ...] = ()
            if isinstance(source, GitHubSource):
                info = (f"fetched {fetched.repository} at {fetched.snapshot}",)
            elif isinstance(source, ZipSource):
                info = (f"extracted {source.path.name}",)
            files = sum(1 for f in doc.files if f.status == "analyzed")
            unresolved = sum(1 for e in doc.edges if e.confidence == "unresolved")
            report = _Report(info, tuple(warnings), files, len(doc.edges), unresolved, doc.snapshot)
    except _StoreFailed as exc:
        _log("error", exc.message)
        return exc.status
    except BadInput as exc:
        _log("error", exc.message)
        return EXIT_USAGE
    except LimitExceeded as exc:
        _log("error", _LIMIT_MESSAGES[exc.limit].format(observed=exc.observed, value=exc.value))
        return EXIT_LIMIT
    except (UnsafeArchive, InvalidArchive) as exc:
        _log("error", exc.message)
        return EXIT_ARCHIVE
    except RemoteError as exc:
        _log("error", exc.message)
        return EXIT_REMOTE
    except KeyboardInterrupt:
        _log("error", "interrupted")
        return EXIT_INTERRUPTED

    if out is None:
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
    else:
        try:
            _write_atomic(out, data)
        except OSError as exc:
            _log("error", f"cannot write {args.out}: {exc.strerror or exc}")
            return EXIT_USAGE

    for line in report.info:
        _log("info", line)
    for path in report.warnings:
        _log("warning", f"ignoring {path}: not valid JSON-with-comments")
    _log(
        "info",
        f"analyzed {report.files} files, {report.edges} edges ({report.unresolved} unresolved), snapshot {report.snapshot}",
    )
    return EXIT_OK
