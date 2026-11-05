"""SC-002 and SC-004: reuse under 2 s; graph of a 5,000-file snapshot under 2 s, a line range under 0.5 s."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from archives import make_tar_gz
from conftest import analyze_dir, run_analyze
from fake_github import FakeGitHub
from graphora.api import create_app
from graphora.ingest import github

pytestmark = [pytest.mark.slow, pytest.mark.db]


def test_five_thousand_files(store, tmp_path):
    for p in range(50):
        pkg = tmp_path / f"pkg{p}"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        for m in range(99):
            imports = "\n".join(f"from pkg{(p + k) % 50} import mod{(m + k) % 99}" for k in (1, 2, 3))
            (pkg / f"mod{m}.py").write_text(f"{imports}\n\n\nclass C{m}:\n    def run(self):\n        return {m}\n")
    analysis = analyze_dir(tmp_path)
    assert len(analysis.doc.files) == 5000
    store.put("big", analysis)
    client = TestClient(create_app(store))
    params = {"repository": "big", "snapshot": analysis.doc.snapshot}

    start = time.monotonic()
    graph = client.get("/api/v1/graph", params=params)
    graph_seconds = time.monotonic() - start
    start = time.monotonic()
    lines = client.get("/api/v1/file", params={**params, "path": "pkg7/mod42.py", "start": 1, "end": 3})
    file_seconds = time.monotonic() - start

    assert graph.status_code == 200 and lines.status_code == 200
    assert graph_seconds < 2, f"graph took {graph_seconds:.2f}s"
    assert file_seconds < 0.5, f"file took {file_seconds:.2f}s"


def test_github_reuse_under_two_seconds(store, database_url, monkeypatch):
    sha = "0123456789abcdef0123456789abcdef01234567"
    fake = FakeGitHub()
    monkeypatch.setattr(github, "_open", fake)
    monkeypatch.setenv("GRAPHORA_DATABASE_URL", database_url)
    fake.serve("https://api.github.com/repos/o/r/commits/HEAD", body=sha.encode())
    entries = [("o-r-0", "dir")] + [(f"o-r-0/m{i}.py", "file", f"import m{(i + 1) % 2000}\n") for i in range(2000)]
    fake.serve(f"https://codeload.github.com/o/r/tar.gz/{sha}", body=make_tar_gz(entries, sha))
    assert run_analyze("https://github.com/o/r", "--store")[0] == 0

    start = time.monotonic()
    code, _, err = run_analyze("https://github.com/o/r", "--store")
    seconds = time.monotonic() - start
    assert code == 0 and "reused" in err
    assert seconds < 2, f"reuse took {seconds:.2f}s"
