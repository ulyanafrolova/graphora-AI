"""`graphora analyze` (contracts/cli.md)."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from graphora.graph.build import build
from graphora.graph.serialize import dumps
from graphora.ingest.walk import Deadline, LimitExceeded

EXIT_OK, EXIT_USAGE, EXIT_LIMIT = 0, 2, 3

_LIMIT_MESSAGES = {
    "files": "file limit exceeded: at least {observed} files > --max-files {value}",
    "bytes": "size limit exceeded: at least {observed} bytes > --max-bytes {value}",
    "seconds": "time limit exceeded: {observed}s > --max-seconds {value}",
}


def _log(level: str, message: str) -> None:
    print(f"graphora: {level}: {message}", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graphora")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="build the import graph of a local folder")
    analyze.add_argument("dir")
    analyze.add_argument("--out")
    analyze.add_argument("--max-files", type=int, default=5000)
    analyze.add_argument("--max-bytes", type=int, default=50 * 1024 * 1024)
    analyze.add_argument("--max-seconds", type=float, default=300)
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


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    root = Path(args.dir)
    if not root.is_dir():
        _log("error", f"not a directory: {args.dir}")
        return EXIT_USAGE
    root = root.resolve()
    out = Path(args.out).resolve() if args.out else None
    if out is not None and (out == root or root in out.parents):
        _log("error", "--out must not be inside the analyzed folder")
        return EXIT_USAGE

    try:
        doc, warnings = build(root, args.max_files, args.max_bytes, Deadline(args.max_seconds))
    except LimitExceeded as exc:
        _log("error", _LIMIT_MESSAGES[exc.limit].format(observed=exc.observed, value=exc.value))
        return EXIT_LIMIT

    data = dumps(doc)
    if out is None:
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
    else:
        try:
            _write_atomic(out, data)
        except OSError as exc:
            _log("error", f"cannot write {args.out}: {exc.strerror or exc}")
            return EXIT_USAGE

    for path in warnings:
        _log("warning", f"ignoring {path}: not valid JSON-with-comments")
    files = sum(1 for f in doc.files if f.status == "analyzed")
    unresolved = sum(1 for e in doc.edges if e.confidence == "unresolved")
    _log("info", f"analyzed {files} files, {len(doc.edges)} edges ({unresolved} unresolved), snapshot {doc.snapshot}")
    return EXIT_OK
