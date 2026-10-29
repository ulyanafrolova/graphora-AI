"""Fetched content is never run (constitution Principle I; specs/002-repo-ingest FR-010)."""

import os
import subprocess

import pytest

from archives import make_tar_gz, make_zip
from conftest import run_analyze
from fake_github import FakeGitHub
from graphora.ingest import github

SHA = "0123456789abcdef0123456789abcdef01234567"


def _entries(marker):
    write = f"open({str(marker)!r}, 'w').close()\n"
    hook = f"#!/bin/sh\ntouch {marker}\n"
    return [
        ("p", "dir"),
        ("p/setup.py", "file", write, 0o755),
        ("p/conftest.py", "file", write),
        ("p/main.py", "file", "import setup\n"),
        ("p/package.json", "file", '{"scripts": {"postinstall": "touch ' + str(marker) + '"}}'),
        ("p/.git/hooks/post-checkout", "file", hook, 0o755),
    ]


@pytest.fixture
def no_subprocess(monkeypatch):
    calls = []

    def record(*args, **kwargs):
        calls.append(args)
        raise AssertionError("subprocess started")

    monkeypatch.setattr(subprocess, "Popen", record)
    monkeypatch.setattr(os, "system", record)
    return calls


def test_github_tarball_is_not_run(tmp_path, monkeypatch, no_subprocess):
    marker = tmp_path / "RAN"
    fake = FakeGitHub()
    fake.serve("https://api.github.com/repos/o/r/commits/HEAD", body=SHA.encode())
    fake.serve(f"https://codeload.github.com/o/r/tar.gz/{SHA}", body=make_tar_gz(_entries(marker), SHA))
    monkeypatch.setattr(github, "_open", fake)
    code, _, err = run_analyze("https://github.com/o/r")
    assert code == 0, err
    assert not marker.exists() and no_subprocess == []


def test_zip_is_not_run(tmp_path, no_subprocess):
    marker = tmp_path / "RAN"
    path = tmp_path / "p.zip"
    path.write_bytes(make_zip(_entries(marker)))
    code, _, err = run_analyze(path)
    assert code == 0, err
    assert not marker.exists() and no_subprocess == []
