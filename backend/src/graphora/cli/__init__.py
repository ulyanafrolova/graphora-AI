"""`graphora analyze`, `graphora serve`, `graphora query`, `graphora mcp` and `graphora ask` (contracts/cli.md; 005:
specs/005-storage-http-api/contracts/cli.md; 004: specs/004-graph-queries/contracts/cli.md; 012:
specs/012-agents/contracts/cli.md)."""

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
from graphora.graph.results import history_line
from graphora.graph.serialize import dumps
from graphora.history import with_history
from graphora.ingest.errors import BadInput, InvalidArchive, RemoteError, UnsafeArchive
from graphora.ingest.fetch import IngestLimits, fetch_snapshot, with_skipped
from graphora.ingest.source import GitHubSource, LocalSource, Source, ZipSource, parse_source
from graphora.ingest.walk import Deadline, LimitExceeded
from graphora.pipeline.messages import limit_message

EXIT_OK, EXIT_USAGE, EXIT_LIMIT = 0, 2, 3
EXIT_ARCHIVE, EXIT_REMOTE, EXIT_STORE, EXIT_INTERRUPTED = 4, 5, 6, 130
EXIT_GRAPH, EXIT_NOT_FOUND, EXIT_MODEL = 7, 8, 9



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
    history: str


def _report_from_bytes(info: tuple[str, ...], warnings: tuple[str, ...], data: bytes) -> _Report:
    from graphora.graph.load import loads
    from graphora.graph.results import history_line

    doc = loads(data)
    files = sum(1 for f in doc.files if f.status == "analyzed")
    unresolved = sum(1 for e in doc.edges if e.confidence == "unresolved")
    return _Report(info, warnings, files, len(doc.edges), unresolved, doc.snapshot, history_line(doc.history))


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
    analyze.add_argument("--no-history", action="store_true", help="do not read the git history (no hotspots)")
    serve = commands.add_parser("serve", help="serve stored analyses over a read-only HTTP API")
    serve.add_argument("--database", help="PostgreSQL URL (default: $GRAPHORA_DATABASE_URL)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--workers", type=int, default=1, help="jobs running at the same time")
    serve.add_argument("--queue", type=int, default=20, help="jobs that may wait")
    serve.add_argument("--asks", type=int, default=1, help="questions answered at the same time (POST /api/v1/ask)")
    serve.add_argument("--model", help="the agents' model, provider:model (default: $GRAPHORA_MODEL or ollama:qwen3:8b)")
    serve.add_argument("--ui", help="a built UI folder to serve (default: $GRAPHORA_UI_DIR, else frontend/dist if built)")
    serve.add_argument("--work-dir", help="folder for uploads and extracted snapshots (default: <temp>/graphora-jobs)")
    serve.add_argument("--max-files", type=int, default=5000)
    serve.add_argument("--max-bytes", type=int, default=50 * 1024 * 1024)
    serve.add_argument("--max-seconds", type=float, default=300)
    serve.add_argument("--max-archive-bytes", type=int, default=IngestLimits.max_archive_bytes)
    serve.add_argument("--max-extract-bytes", type=int, default=IngestLimits.max_extract_bytes)
    serve.add_argument("--max-entries", type=int, default=IngestLimits.max_entries)
    query = commands.add_parser("query", help="answer one question about a graph document")
    query.add_argument("graph", help="a graph JSON written by `graphora analyze`, or - for standard input")
    query.add_argument("question", choices=_QUESTIONS)
    query.add_argument("target", nargs="?", help="a node id, a file path or an external package name; for definitions, a name")
    query.add_argument("--format", choices=("text", "json"), default="text")
    query.add_argument("--limit", type=int)
    query.add_argument("--no-type-only", action="store_true", help="leave out type-only links")
    query.add_argument("--symbol", help="dependents: only edges of this imported name")
    query.add_argument("--max-depth", type=int, help="impact: stop at this distance")
    query.add_argument("--follow-barrels", action="store_true", help="dependents and impact: see through re-exports (index.ts, Python __init__.py)")
    query.add_argument(
        "--level",
        choices=("file", "project"),
        default="file",
        help="dependencies, dependents, impact, cycles: answer for C# projects instead of files",
    )
    mcp = commands.add_parser("mcp", help="serve one snapshot to coding agents over MCP on standard input/output")
    mcp.add_argument("--graph", help="a graph JSON written by `graphora analyze`")
    mcp.add_argument("--repository", help="store mode: a stored repository name")
    mcp.add_argument("--snapshot", help="store mode: a stored snapshot id")
    mcp.add_argument("--database", help="store mode: PostgreSQL URL (default: $GRAPHORA_DATABASE_URL)")
    ask = commands.add_parser("ask", help="answer a question about one snapshot with the agents; facts are verified")
    ask.add_argument("question", help="the question, in quotes")
    ask.add_argument("--graph", help="a graph JSON written by `graphora analyze` (- for standard input)")
    ask.add_argument("--repository", help="store mode: a stored repository name")
    ask.add_argument("--snapshot", help="store mode: a stored snapshot id")
    ask.add_argument("--database", help="store mode: PostgreSQL URL (default: $GRAPHORA_DATABASE_URL)")
    ask.add_argument("--model", help="provider:model (default: $GRAPHORA_MODEL or ollama:qwen3:8b)")
    ask.add_argument("--no-summary", action="store_true", help="no model summary; the summary is built by code")
    ask.add_argument("--json", action="store_true", help="print the answer and trace as JSON")
    ask.add_argument("--trace", metavar="FILE", help="also write the trace as JSON lines to FILE (- for stderr)")
    return parser


_QUESTIONS = (
    "dependencies",
    "dependents",
    "impact",
    "neighbors",
    "cycles",
    "key-files",
    "hotspots",
    "overview",
    "definitions",
    "projects",
    "components",
)
_WITH_TARGET = ("dependencies", "dependents", "impact", "neighbors", "definitions")
_LEVEL_QUESTIONS = ("dependencies", "dependents", "impact", "cycles")
_OPTION_QUESTIONS = {"symbol": ("dependents",), "max_depth": ("impact",), "follow_barrels": ("dependents", "impact")}


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
    if args.command == "query":
        return _query(args)
    if args.command == "mcp":
        return _mcp(args)
    if args.command == "ask":
        return _ask(args)

    # SIGTERM must also unwind through fetch_snapshot so the temp folder is removed (research § R11).
    in_main_thread = threading.current_thread() is threading.main_thread()
    previous = signal.signal(signal.SIGTERM, _raise_interrupt) if in_main_thread else None
    try:
        return _analyze(args)
    finally:
        if in_main_thread:
            signal.signal(signal.SIGTERM, previous)


def _query(args: argparse.Namespace) -> int:
    """One question about a graph document (specs/004-graph-queries contracts/cli.md). Kept apart from `_analyze`."""
    from graphora.graph import queries
    from graphora.graph.load import InvalidGraph, loads
    from graphora.graph.results import dumps, render_text

    question = args.question
    if question in _WITH_TARGET and args.target is None:
        _log("error", f"{question} needs a target")
        return EXIT_USAGE
    if question not in _WITH_TARGET and args.target is not None:
        _log("error", f"{question} takes no target")
        return EXIT_USAGE
    for option, allowed in _OPTION_QUESTIONS.items():
        if getattr(args, option) not in (None, False) and question not in allowed:
            _log("error", f"--{option.replace('_', '-')} is only for {' and '.join(allowed)}")
            return EXIT_USAGE
    if question in ("overview", "projects") and (args.limit is not None or args.no_type_only):
        _log("error", f"{question} takes only --format")
        return EXIT_USAGE
    if question == "components" and args.limit is not None:
        _log("error", "components takes only --no-type-only and --format")
        return EXIT_USAGE
    if question == "definitions" and args.no_type_only:
        _log("error", "definitions takes only --limit and --format")
        return EXIT_USAGE

    if args.level == "project":
        if question not in _LEVEL_QUESTIONS:
            _log("error", f"--level is only for {', '.join(_LEVEL_QUESTIONS)}")
            return EXIT_USAGE
        flags = (("--symbol", args.symbol), ("--follow-barrels", args.follow_barrels), ("--no-type-only", args.no_type_only))
        given = [flag for flag, value in flags if value]
        if given:
            _log("error", f"{' and '.join(given)} cannot be used with --level project")
            return EXIT_USAGE

    options: dict[str, object] = {"include_type_only": not args.no_type_only, "limit": args.limit}
    if question in _LEVEL_QUESTIONS and args.level == "project":
        options["level"] = "project"
    if question == "dependents":
        options.update(symbol=args.symbol, follow_barrels=args.follow_barrels)
    elif question == "impact":
        options.update(max_depth=args.max_depth, follow_barrels=args.follow_barrels)
    asks = {
        "dependencies": queries.dependencies,
        "dependents": queries.dependents,
        "impact": queries.impact,
        "cycles": queries.cycles,
        "neighbors": queries.neighbors,
        "key-files": queries.key_files,
        "hotspots": queries.hotspots,
    }
    if question in ("key-files", "hotspots") and args.limit is None:
        options["limit"] = 10

    try:
        data = sys.stdin.buffer.read() if args.graph == "-" else Path(args.graph).read_bytes()
    except OSError as exc:
        _log("error", f"cannot read {args.graph}: {exc.strerror or exc}")
        return EXIT_USAGE
    try:
        ix = queries.index(loads(data))
        target = (args.target,) if question in _WITH_TARGET else ()
        if question == "overview":
            answer = queries.overview(ix)
        elif question == "projects":
            answer = queries.projects(ix)
        elif question == "definitions":
            answer = queries.definitions(ix, args.target, limit=args.limit)
        elif question == "components":
            answer = queries.components(ix, include_type_only=not args.no_type_only)
        else:
            answer = asks[question](ix, *target, **options)
    except InvalidGraph as exc:
        _log("error", f"invalid graph: {exc.message}")
        return EXIT_GRAPH
    except queries.NodeNotFound as exc:
        _log("error", exc.message)
        return EXIT_NOT_FOUND
    except ValueError as exc:
        _log("error", str(exc))
        return EXIT_USAGE

    out = dumps(answer) if args.format == "json" else render_text(answer).encode("utf-8")
    sys.stdout.buffer.write(out)
    sys.stdout.flush()
    return EXIT_OK


def _served(args: argparse.Namespace, command: str) -> object:
    """The snapshot of `--graph`, or of `--repository` and `--snapshot` from the store; an exit code on failure
    (specs/006-mcp-server contracts/cli.md, shared by `ask`)."""
    from graphora.graph.load import InvalidGraph
    from graphora.graph.load import loads as load_graph
    from graphora.graph.queries import index
    from graphora.mcp import PairNotFound, Served, from_graph_file, from_store
    from graphora.store import StoreUnavailable

    store_mode = args.repository is not None or args.snapshot is not None
    if args.graph is None and not store_mode:
        _log("error", "give --graph FILE, or --repository and --snapshot")
        return EXIT_USAGE
    if args.graph is not None and store_mode:
        _log("error", "--graph cannot be combined with --repository or --snapshot")
        return EXIT_USAGE
    if store_mode and (args.repository is None or args.snapshot is None):
        _log("error", "--repository and --snapshot go together")
        return EXIT_USAGE
    if args.graph == "-" and command == "mcp":
        _log("error", "--graph - is not allowed: standard input carries the MCP protocol")
        return EXIT_USAGE
    if args.graph is not None and args.database is not None:
        _log("error", "--database is only for store mode")
        return EXIT_USAGE

    try:
        if store_mode:
            url = _database_url(args.database)
            if url is None:
                raise StoreUnavailable("no database URL: use --database or GRAPHORA_DATABASE_URL")
            return from_store(url, args.repository, args.snapshot)
        if args.graph == "-":
            return Served(index(load_graph(sys.stdin.buffer.read())))
        return from_graph_file(args.graph)
    except OSError as exc:
        _log("error", f"cannot read {args.graph}: {exc.strerror or exc}")
        return EXIT_USAGE
    except StoreUnavailable as exc:
        _log("error", f"store unavailable: {exc.reason}")
        return EXIT_STORE
    except InvalidGraph as exc:
        _log("error", f"invalid graph: {exc.message}")
        return EXIT_GRAPH
    except PairNotFound as exc:
        _log("error", exc.message)
        return EXIT_NOT_FOUND


def _mcp(args: argparse.Namespace) -> int:
    """`graphora mcp` (specs/006-mcp-server contracts/cli.md). Only the protocol may write to stdout."""
    from graphora.mcp import create_server

    served = _served(args, "mcp")
    if isinstance(served, int):
        return served
    try:
        create_server(served).run("stdio")
    finally:
        if served.store is not None:
            served.store.close()
    return EXIT_OK


def _ask(args: argparse.Namespace) -> int:
    """`graphora ask` (specs/012-agents contracts/cli.md)."""
    from graphora.agents import ModelUnavailable, ask, model, render_answer

    if not args.question.strip():
        _log("error", "the question must not be empty")
        return EXIT_USAGE
    setting = args.model or model.setting_from_env()
    try:
        chat = model.model_from_setting(setting)
    except ModelUnavailable as exc:
        _log("error", exc.message)
        return EXIT_MODEL
    served = _served(args, "ask")
    if isinstance(served, int):
        return served
    try:
        run = ask(args.question, served, model=chat, setting=setting, summary=not args.no_summary)
    finally:
        if served.store is not None:
            served.store.close()
    if run.answer.end == "model_failed" and not run.answer.facts and not run.answer.likely and not run.answer.hypotheses:
        _log("error", run.error or f"model {setting} unavailable at {model.address(setting)}: the run failed")
        return EXIT_MODEL
    if args.trace is not None:
        lines = "".join(json.dumps(e.to_dict(), sort_keys=True, ensure_ascii=False) + "\n" for e in run.trace)
        if args.trace == "-":
            sys.stderr.write(lines)
        else:
            Path(args.trace).write_text(lines, encoding="utf-8")
    sys.stdout.write(run.to_json() if args.json else render_answer(run.answer))
    return EXIT_OK


def _ui_dir(option: str | None) -> Path | None:
    """`--ui`, `$GRAPHORA_UI_DIR`, or `frontend/dist` of this checkout when it was built (specs/019-frontend R7)."""
    chosen = option or os.environ.get("GRAPHORA_UI_DIR")
    if chosen:
        return Path(chosen)
    built = Path(__file__).resolve().parents[4] / "frontend" / "dist"
    return built if (built / "index.html").is_file() else None


def _serve(args: argparse.Namespace) -> int:
    from graphora.pipeline import LIMIT_KEYS, PipelineLimits
    from graphora.store import Store, StoreUnavailable

    for name in ("workers", "queue", "asks", *LIMIT_KEYS):
        if getattr(args, name) < 1:
            _log("error", f"--{name.replace('_', '-')} must be at least 1")
            return EXIT_USAGE
    ui = _ui_dir(args.ui)
    if ui is not None and not (ui / "index.html").is_file():
        _log("error", f"no built UI in {ui}: run `make web-build` or leave out --ui")
        return EXIT_USAGE
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

        from graphora.agents import setting_from_env
        from graphora.api import create_app
        from graphora.api.ask import AskService
        from graphora.pipeline.jobs import JobRunner, WorkDirInUse

        limits = PipelineLimits(**{key: getattr(args, key) for key in LIMIT_KEYS})
        work_dir = Path(args.work_dir) if args.work_dir else None
        runner = JobRunner(url, limits, workers=args.workers, queue_size=args.queue, work_dir=work_dir)
        try:
            runner.start()
        except WorkDirInUse:
            _log("error", "work folder in use by another graphora serve: use --work-dir")
            return EXIT_USAGE
        except OSError as exc:
            _log("error", f"cannot create work folder: {exc.strerror or exc}")
            return EXIT_USAGE
        asks = AskService(store, url, args.model or setting_from_env(), limit=args.asks)
        try:
            # open streams are cancelled 5 s after Ctrl-C; their runs stop at the next step (013 research R5)
            uvicorn.run(create_app(store, runner, asks, ui), host=args.host, port=args.port, timeout_graceful_shutdown=5)
        finally:
            try:
                asks.stop()
            finally:
                runner.stop()
    finally:
        store.close()
    return EXIT_OK


def _analyze_and_store(
    args: argparse.Namespace, source: Source, limits: IngestLimits, deadline: Deadline
) -> tuple[bytes, _Report]:
    """The `--store` path (005 contracts/cli.md, research § R6). Nothing is printed here.

    The flow itself is `graphora.pipeline.run_pipeline`, shared with `graphora serve` (010 research § R2).
    """
    from graphora.pipeline import PipelineLimits, run_pipeline
    from graphora.store import InvalidAnalysis, Store, StoreUnavailable

    url = _database_url(args.database)
    try:
        if url is None:
            raise StoreUnavailable("no database URL: use --database or GRAPHORA_DATABASE_URL")
        store = Store.open(url)
    except StoreUnavailable as exc:
        raise _StoreFailed(EXIT_STORE, f"store unavailable: {exc.reason}") from None
    try:
        pipeline_limits = PipelineLimits(
            args.max_files, args.max_bytes, args.max_seconds, limits.max_archive_bytes, limits.max_extract_bytes,
            limits.max_entries,
        )
        result = run_pipeline(source, pipeline_limits, store, deadline, history=not args.no_history)
        saved = result.analysis
        info = () if result.fetched is None else (result.fetched,)
        info += (f"{result.action} {saved.repository} {saved.snapshot}",)
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
                doc = with_history(doc, fetched, deadline, not args.no_history, limits.max_archive_bytes)
                data = dumps(doc)
            info: tuple[str, ...] = ()
            if isinstance(source, GitHubSource):
                info = (f"fetched {fetched.repository} at {fetched.snapshot}",)
            elif isinstance(source, ZipSource):
                info = (f"extracted {source.path.name}",)
            files = sum(1 for f in doc.files if f.status == "analyzed")
            unresolved = sum(1 for e in doc.edges if e.confidence == "unresolved")
            report = _Report(info, tuple(warnings), files, len(doc.edges), unresolved, doc.snapshot, history_line(doc.history))
    except _StoreFailed as exc:
        _log("error", exc.message)
        return exc.status
    except BadInput as exc:
        _log("error", exc.message)
        return EXIT_USAGE
    except LimitExceeded as exc:
        _log("error", limit_message(exc, "cli"))
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
        if path.lower().endswith((".sln", ".slnx")):
            _log("warning", f"ignoring {path}: not a readable solution file")
        elif path.lower().endswith(".csproj") or path.rsplit("/", 1)[-1] == "Directory.Build.props":
            _log("warning", f"ignoring {path}: not well-formed XML or has a DOCTYPE")
        else:
            _log("warning", f"ignoring {path}: not valid JSON-with-comments")
    _log(
        "info",
        f"analyzed {report.files} files, {report.edges} edges ({report.unresolved} unresolved), snapshot {report.snapshot}",
    )
    _log("info", report.history)
    return EXIT_OK
