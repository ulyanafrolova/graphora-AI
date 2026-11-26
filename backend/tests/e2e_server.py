"""Graphora for the Playwright tests: fixtures stored, a scripted model, the built UI (specs/019-frontend research § R13).

Run from `backend/`: `uv run python tests/e2e_server.py --port 8765`. Not collected by pytest."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "unit"), str(HERE / "integration")]

import uvicorn  # noqa: E402

from conftest import analyze_dir, analyze_fixture  # noqa: E402
from graphora.agents.claims import ClaimItem, ClaimsReply  # noqa: E402
from graphora.api import create_app  # noqa: E402
from graphora.api.ask import AskService  # noqa: E402
from graphora.graph.build import Analysis  # noqa: E402
from graphora.graph.load import loads  # noqa: E402
from graphora.pipeline import PipelineLimits  # noqa: E402
from graphora.pipeline.jobs import JobRunner  # noqa: E402
from graphora.store import Store  # noqa: E402
from history_repos import make_repo  # noqa: E402
from scripted_model import call, scripted  # noqa: E402
from test_query_performance import _graph  # noqa: E402

FIXTURES = ("py-cycles", "ts-app", "mixed-fullstack", "csharp-multiproject")
UI = HERE.parents[1] / "frontend" / "dist"
HISTORY = [
    {"files": {"app/a.py": b"import app.b\n", "app/b.py": b"x = 1\n", "app/c.py": b"import app.a\n"}},
    {"files": {"app/b.py": b"x = 2\n"}},
    {"files": {"app/a.py": b"import app.b\nimport os\n"}},
    {"files": {"app/b.py": b"x = 3\n"}},
]
# the strings of frontend/tests/unit/hostile.test.tsx; they must show as text (SC-004)
HOSTILE = ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "javascript:alert(1)", "**md**", "[a](javascript:x)"]
HOSTILE_NAME = "<img src=x onerror=alert(1)>"


def hostile_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "app.py").write_text("import helpers\n" + "".join(f"# {h}\n" for h in HOSTILE), encoding="utf-8")
    (root / "helpers.py").write_text("def javascript_alert():\n    return '<script>alert(1)</script>'\n", encoding="utf-8")
    for name in ("<img src=x onerror=alert(1)>.py", "**md**.py", "javascript:alert(1).py"):
        (root / name).write_text("x = '<img src=x onerror=alert(1)>'\n", encoding="utf-8")
    return root


def replies() -> list:
    """One answer about loop/a.py of py-cycles: two verified facts, one hypothesis naming a hostile path (SC-004)."""
    return [
        call("dependents", target="loop/a.py"),
        "loop/a.py is imported by c1 and c2",
        "no tools",
        ClaimsReply(
            claims=[
                ClaimItem(statement="loop/c.py imports loop/a.py", cite="c1"),
                ClaimItem(statement="user.py imports loop/a.py", cite="c2"),
                ClaimItem(statement="the frontend calls loop/a.py", path=f"{HOSTILE_NAME}.ts", line=1, target="loop/a.py"),
            ]
        ),
        "nothing more",
        "no tools",
        ClaimsReply(claims=[]),
        "Changing loop/a.py breaks loop/c.py and user.py.",
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    url = os.environ.get("GRAPHORA_TEST_DATABASE_URL")
    if not url:
        sys.exit("GRAPHORA_TEST_DATABASE_URL is not set")

    store = Store.open(url)
    store._conn.execute("TRUNCATE files, analyses, blobs")
    for name in FIXTURES:
        store.put(name, analyze_fixture(name))
    work = Path(tempfile.mkdtemp(prefix="graphora-e2e-"))
    make_repo(work / "history-app", HISTORY)
    store.put("history-app", analyze_dir(work / "history-app"))
    store.put(HOSTILE_NAME, analyze_dir(hostile_repo(work / "hostile")))
    store.put("stale-app", analyze_fixture("py-cycles"))  # analyzed by an older version: errors.spec.ts
    store._conn.execute("UPDATE analyses SET schema_version = schema_version - 1 WHERE repository = 'stale-app'")
    large = loads(_graph())  # the 5,000-file graph of test_query_performance (SC-003)
    store.put("large", Analysis(doc=large, warnings=(), contents={f.path: b"x = 1\n" for f in large.files}))

    runner = JobRunner(url, PipelineLimits(), work_dir=work / "jobs")
    runner.start()
    asks = AskService(store, url, "scripted:e2e", model_factory=lambda setting: scripted(*replies())[0])
    app = create_app(store, runner, asks, UI if (UI / "index.html").is_file() else None)
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        asks.stop(timeout=10)
        runner.stop()
        store.close()


if __name__ == "__main__":
    main()
