from graphora.adapters.python.extract import extract
from graphora.graph.model import Definition


def _imports(src: str):
    return [(r.kind, r.module, r.level, r.names, r.line, r.column) for r in extract(src.encode()).imports]


def test_import_forms():
    src = (
        "import a\n"
        "import a.b as c, d\n"
        "from a import b, c as z\n"
        "from . import x\n"
        "from ..y import *\n"
        "from m import (\n"
        "    p,\n"
        "    q,\n"
        ")\n"
    )
    assert _imports(src) == [
        ("import", "a", 0, (None,), 1, 1),
        ("import", "a.b", 0, (None,), 2, 1),
        ("import", "d", 0, (None,), 2, 1),
        ("from", "a", 0, ("b", "c"), 3, 1),
        ("from", None, 1, ("x",), 4, 1),
        ("from", "y", 2, ("*",), 5, 1),
        ("from", "m", 0, ("p", "q"), 6, 1),
    ]


def test_future_import():
    assert _imports("from __future__ import annotations\n") == [("from", "__future__", 0, ("annotations",), 1, 1)]


def test_column_counts_code_points():
    records = extract("x = 'ü'; import os\n".encode()).imports
    assert (records[0].line, records[0].column) == (1, 10)


def test_imports_in_every_scope():
    src = "def f():\n    import a\nif X:\n    import b\ntry:\n    import c\nexcept ImportError:\n    import d\nclass K:\n    import e\n"
    assert [r.module for r in extract(src.encode()).imports] == ["a", "b", "c", "d", "e"]


def test_dynamic_forms():
    src = (
        "import importlib\n"
        "import importlib as il\n"
        "from importlib import import_module as im\n"
        "importlib.import_module(name)\n"
        'importlib.import_module("p.alpha")\n'
        '__import__("json")\n'
        'il.import_module(".rel")\n'
        'im(f"p.{x}")\n'
        'importlib.import_module("p", package="q")\n'
        'importlib.import_module("a" "b")\n'
        'other.import_module("x")\n'
    )
    dynamic = [(r.module, r.literal, r.text) for r in extract(src.encode()).imports if r.kind == "dynamic"]
    assert dynamic == [
        (None, False, "importlib.import_module(name)"),
        ("p.alpha", True, 'importlib.import_module("p.alpha")'),
        ("json", True, '__import__("json")'),
        (None, False, 'il.import_module(".rel")'),
        (None, False, 'im(f"p.{x}")'),
        (None, False, 'importlib.import_module("p", package="q")'),
        (None, False, 'importlib.import_module("a" "b")'),
    ]


def test_bare_import_module_needs_from_import():
    dynamic = [r for r in extract(b'import_module("x")\n').imports if r.kind == "dynamic"]
    assert dynamic == []


def test_definitions():
    src = (
        "class A:\n"
        "    def m(self):\n"
        "        def inner():\n"
        "            pass\n"
        "    @property\n"
        "    def p(self):\n"
        "        pass\n"
        "    class Nested:\n"
        "        pass\n"
        "@decorator\n"
        "def f():\n"
        "    pass\n"
        "async def g():\n"
        "    pass\n"
        "if X:\n"
        "    def hidden():\n"
        "        pass\n"
    )
    assert extract(src.encode()).definitions == (
        Definition("class", "A", 1),
        Definition("method", "A.m", 2),
        Definition("method", "A.p", 6),
        Definition("function", "f", 11),
        Definition("function", "g", 13),
    )


def test_syntax_error_keeps_earlier_imports():
    facts = extract(b"import os\n\ndef broken(:\n    pass\n")
    assert facts.has_error
    assert [r.module for r in facts.imports] == ["os"]
