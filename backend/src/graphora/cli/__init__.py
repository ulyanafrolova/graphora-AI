"""`graphora analyze` (contracts/cli.md)."""

from __future__ import annotations

import argparse
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
from graphora.ingest.source import GitHubSource, LocalSource, ZipSource, parse_source
from graphora.ingest.walk import Deadline, LimitExceeded

EXIT_OK, EXIT_USAGE, EXIT_LIMIT = 0, 2, 3
EXIT_ARCHIVE, EXIT_REMOTE, EXIT_INTERRUPTED = 4, 5, 130

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
    return parser


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

    # SIGTERM must also unwind through fetch_snapshot so the temp folder is removed (research § R11).
    in_main_thread = threading.current_thread() is threading.main_thread()
    previous = signal.signal(signal.SIGTERM, _raise_interrupt) if in_main_thread else None
    try:
        return _analyze(args)
    finally:
        if in_main_thread:
            signal.signal(signal.SIGTERM, previous)


def _analyze(args: argparse.Namespace) -> int:
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
        with fetch_snapshot(source, limits, deadline) as fetched:
            doc, warnings = build(fetched.root, args.max_files, args.max_bytes, deadline, snapshot=fetched.snapshot)
            doc = with_skipped(doc, fetched.skipped)
            data = dumps(doc)
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

    if isinstance(source, GitHubSource):
        _log("info", f"fetched {fetched.repository} at {fetched.snapshot}")
    elif isinstance(source, ZipSource):
        _log("info", f"extracted {source.path.name}")
    for path in warnings:
        _log("warning", f"ignoring {path}: not valid JSON-with-comments")
    files = sum(1 for f in doc.files if f.status == "analyzed")
    unresolved = sum(1 for e in doc.edges if e.confidence == "unresolved")
    _log("info", f"analyzed {files} files, {len(doc.edges)} edges ({unresolved} unresolved), snapshot {doc.snapshot}")
    return EXIT_OK
