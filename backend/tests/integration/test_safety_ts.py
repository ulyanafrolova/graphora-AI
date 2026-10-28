"""Constitution Principle I for TS/JS: config files are data, nothing is executed, nothing outside is read."""

import json
import os
import subprocess

import pytest

from conftest import run_analyze


def _tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def _forbid(*_args, **_kwargs):
    raise AssertionError("analysis must not start a process")


def test_ts_config_and_packages_are_data(tmp_path, monkeypatch):
    (tmp_path / "outside.json").write_text(json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@out/*": ["repo/src/*"]}}}))
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "tsconfig.json").write_text(json.dumps({"extends": "../outside.json"}))
    (root / "src" / "x.ts").write_text("export const x = 1;\n")
    (root / "src" / "main.ts").write_text('import { x } from "@out/x";\nimport pkg from "pkg";\n')
    marker = tmp_path / "EXECUTED_MARKER"
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "node_modules" / "pkg" / "index.js").write_text(f'require("fs").writeFileSync({json.dumps(str(marker))}, "x");\n')
    (root / "package.json").write_text(json.dumps({"name": "app", "scripts": {"postinstall": f"touch {marker}"}}))
    before = _tree(root)

    monkeypatch.setattr(subprocess, "Popen", _forbid)
    monkeypatch.setattr(os, "system", _forbid)
    if hasattr(os, "posix_spawn"):
        monkeypatch.setattr(os, "posix_spawn", _forbid)

    code, out, err = run_analyze(root)

    assert code == 0, err
    assert not marker.exists()
    assert _tree(root) == before
    edges = {e["line"]: e for e in json.loads(out)["edges"] if e["source"] == "file:src/main.ts"}
    assert edges[1]["target"] == "ext:npm:@out/x"  # the outside config was not read, so no alias applies
    assert edges[2]["target"] == "ext:npm:pkg"  # node_modules is skipped, never resolved into


@pytest.mark.parametrize("extends", ["/etc/tsconfig.json", "@tsconfig/node20/tsconfig.json"])
def test_extends_outside_targets_ignored(tmp_path, extends):
    (tmp_path / "tsconfig.json").write_text(json.dumps({"extends": extends, "compilerOptions": {"baseUrl": "src"}}))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "util.ts").write_text("")
    (tmp_path / "a.ts").write_text('import u from "util";\n')
    code, out, err = run_analyze(tmp_path)
    assert code == 0, err
    edge = next(e for e in json.loads(out)["edges"])
    assert edge["target"] == "file:src/util.ts"
