"""Extractor versions in the graph must change whenever the code or parser pin behind them changes (constitution II).

Each component's fingerprint is a hash of its source files and pinned parser versions. `extractor_versions.json`
records one fingerprint per released version. Changing the code without bumping the version fails here:
bump the version and add a line, or, for a change that cannot alter output (a comment, a rename), replace the
fingerprint of the current version.
"""

import hashlib
import json
from importlib import metadata
from pathlib import Path

import pytest

from graphora.adapters import js, python
from graphora.resolve import js as js_resolve
from graphora.resolve import python as py_resolve

SRC = Path(__file__).resolve().parents[2] / "src" / "graphora"
LOCK = Path(__file__).with_name("extractor_versions.json")

COMPONENTS = {
    "python-adapter": (python.VERSION, ["adapters/python/*.py", "adapters/position.py"], ["tree-sitter", "tree-sitter-python"]),
    "js-adapter": (js.VERSION, ["adapters/js/*.py", "adapters/position.py"], ["tree-sitter", "tree-sitter-typescript", "tree-sitter-javascript"]),
    "python-resolver": (py_resolve.RESOLVER_VERSION, ["resolve/python.py"], []),
    "python-stdlib": (py_resolve.STDLIB_VERSION, ["resolve/data/stdlib_modules.txt"], []),
    "js-resolver": (js_resolve.RESOLVER_VERSION, ["resolve/js.py", "resolve/tsconfig.py"], []),
    "node-builtins": (js_resolve.BUILTINS_VERSION, ["resolve/data/node_builtins.txt"], []),
}


def fingerprint(patterns: list[str], packages: list[str]) -> str:
    h = hashlib.sha256()
    for path in sorted({p for pattern in patterns for p in SRC.glob(pattern)}):
        h.update(path.relative_to(SRC).as_posix().encode() + b"\0" + path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    for package in packages:
        h.update(f"{package}=={metadata.version(package)}\n".encode())
    return h.hexdigest()[:16]


@pytest.mark.parametrize("name", sorted(COMPONENTS))
def test_version_bumped_when_code_changes(name):
    version, patterns, packages = COMPONENTS[name]
    actual = fingerprint(patterns, packages)
    recorded = json.loads(LOCK.read_text(encoding="utf-8")).get(f"{name}@{version}")
    assert recorded == actual, (
        f"{name}@{version} changed (fingerprint {actual}, recorded {recorded}). If the output can change, bump the "
        f"version and add \"{name}@<new>\": \"{actual}\" to {LOCK.name}; otherwise update the current entry."
    )
