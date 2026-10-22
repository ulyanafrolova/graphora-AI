import pytest

from graphora.adapters.python.extract import extract
from graphora.resolve.python import build_index, category, resolve

PATHS = [
    "main.py",
    "pkg/__init__.py",
    "pkg/a.py",
    "pkg/b.py",
    "pkg/sub/__init__.py",
    "pkg/sub/deep.py",
    "ns/mod.py",
    "src/app/__init__.py",
    "src/app/core.py",
    "src/app/core.pyi",
    "src/app/api/__init__.py",
    "src/app/api/routes.py",
    "src/only_stub.pyi",
    "json.py",
]
INDEX = build_index(PATHS)


def _resolve(path, src):
    (record,) = extract(src.encode()).imports
    return [(t.node_id, t.symbol, t.reason) for t in resolve(path, record, INDEX)]


@pytest.mark.parametrize(
    "path, src, expected",
    [
        # import a.b.c
        ("main.py", "import pkg.sub.deep", [("file:pkg/sub/deep.py", None, None)]),
        ("main.py", "import pkg", [("file:pkg/__init__.py", None, None)]),
        ("main.py", "import ns", [("unresolved:ns", None, "namespace_package")]),
        ("main.py", "import pkg.nope", [("unresolved:pkg.nope", None, "not_found")]),
        ("main.py", "import pkg.a.nope", [("unresolved:pkg.a.nope", None, "not_found")]),
        ("main.py", "import requests.adapters", [("ext:requests", None, None)]),
        # from M import n (absolute)
        ("main.py", "from pkg import a", [("file:pkg/a.py", "a", None)]),
        ("main.py", "from pkg.a import helper", [("file:pkg/a.py", "helper", None)]),
        ("main.py", "from pkg import a, nothing", [("file:pkg/a.py", "a", None), ("file:pkg/__init__.py", "nothing", None)]),
        ("main.py", "from ns import mod", [("file:ns/mod.py", "mod", None)]),
        ("main.py", "from ns import missing", [("unresolved:ns.missing", "missing", "not_found")]),
        ("main.py", "from pkg.gone import x", [("unresolved:pkg.gone", "x", "not_found")]),
        ("main.py", "from requests import Session", [("ext:requests", "Session", None)]),
        ("main.py", "from pkg.a import *", [("file:pkg/a.py", "*", None)]),
        # relative
        ("pkg/a.py", "from .b import f", [("file:pkg/b.py", "f", None)]),
        ("pkg/b.py", "from . import a", [("file:pkg/a.py", "a", None)]),
        ("pkg/__init__.py", "from .a import helper", [("file:pkg/a.py", "helper", None)]),
        ("pkg/sub/deep.py", "from .. import b", [("file:pkg/b.py", "b", None)]),
        ("pkg/a.py", "from .missing import x", [("unresolved:pkg.missing", "x", "not_found")]),
        ("pkg/a.py", "from .requests import x", [("unresolved:pkg.requests", "x", "not_found")]),
        ("pkg/a.py", "from ...up import y", [("unresolved:...up", "y", "relative_beyond_top")]),
        ("main.py", "from . import x", [("unresolved:.", "x", "relative_beyond_top")]),
        ("src/app/api/routes.py", "from ..core import Engine", [("file:src/app/core.py", "Engine", None)]),
        # dynamic
        ("main.py", 'import importlib\n', [("ext:importlib", None, None)]),
        ("main.py", '__import__("pkg.a")', [("file:pkg/a.py", None, None)]),
        ("main.py", "__import__(name)", [("unresolved:__import__(name)", None, "dynamic")]),
    ],
)
def test_resolution_table(path, src, expected):
    assert _resolve(path, src) == expected


def test_src_root():
    assert _resolve("tests/t.py", "import app.core") == [("file:src/app/core.py", None, None)]


def test_py_wins_over_pyi():
    assert INDEX.modules["app.core"] == "src/app/core.py"
    assert INDEX.modules["only_stub"] == "src/only_stub.pyi"


def test_root_wins_over_src():
    index = build_index(["app/__init__.py", "src/app/__init__.py"])
    assert index.modules["app"] == "app/__init__.py"


def test_local_wins_over_external():
    assert _resolve("main.py", "import json") == [("file:json.py", None, None)]


def test_stdlib_category():
    assert category("json") == "stdlib"
    assert category("__future__") == "stdlib"
    assert category("requests") == "third_party"
