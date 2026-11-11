"""The definitions query (specs/006-mcp-server spec US2, research § R8)."""

import pytest

from graphora.graph.model import Definition, FileNode
from graphora.graph.queries import definitions, index
from graphora.graph.results import dumps, render_text
from synthetic import edge, make_doc


def py(path, *defs):
    return FileNode(path, "python", tuple(Definition(kind, name, line) for kind, name, line in defs))


def ts(path, *defs):
    return FileNode(path, "typescript", tuple(Definition(k, n, line, tuple(e)) for k, n, line, e in defs), ())


def ix_of(*nodes):
    return index(make_doc([edge("main.py", "auth/service.py")], nodes=nodes))


def found(answer):
    return [(d.path, d.line, d.kind, d.name) for d in answer.definitions]


def test_class_by_name():
    ix = ix_of(py("auth/service.py", ("class", "AuthService", 12)))
    assert found(definitions(ix, "AuthService")) == [("auth/service.py", 12, "class", "AuthService")]


def test_same_name_in_two_files_in_path_order():
    ix = ix_of(py("b/io.py", ("function", "load", 3)), py("a/io.py", ("function", "load", 9)))
    assert found(definitions(ix, "load")) == [("a/io.py", 9, "function", "load"), ("b/io.py", 3, "function", "load")]


def test_method_by_short_and_full_name():
    ix = ix_of(py("log.py", ("class", "Logger", 1), ("method", "Logger.write", 4)))
    expected = [("log.py", 4, "method", "Logger.write")]
    assert found(definitions(ix, "write")) == expected
    assert found(definitions(ix, "Logger.write")) == expected


def test_exported_names_for_ts_only():
    ix = ix_of(ts("ui/Button.tsx", ("class", "Button", 2, ["default", "Button"])), py("auth/service.py", ("class", "Button", 5)))
    by_path = {d.path: d.to_dict() for d in definitions(ix, "Button").definitions}
    assert by_path["ui/Button.tsx"]["exported_as"] == ["Button", "default"]
    assert "exported_as" not in by_path["auth/service.py"]
    assert "exported as Button, default" in render_text(definitions(ix, "Button"))


def test_unknown_name_is_an_empty_answer_with_completeness():
    answer = definitions(ix_of(), "Nothing")
    assert (answer.definitions, answer.total) == ((), 0)
    assert answer.completeness is not None


def test_case_sensitive():
    assert definitions(ix_of(py("auth/service.py", ("class", "AuthService", 1))), "authservice").definitions == ()


def test_order_by_path_line_name():
    ix = ix_of(py("m.py", ("function", "f", 9), ("class", "C", 2), ("method", "C.f", 3)))
    assert [(d.line, d.name) for d in definitions(ix, "f").definitions] == [(3, "C.f"), (9, "f")]


def test_limit():
    ix = ix_of(*[py(f"m{n}.py", ("function", "run", 1)) for n in range(5)])
    answer = definitions(ix, "run", limit=2)
    assert (len(answer.definitions), answer.total, answer.truncated) == (2, 5, True)


def test_answer_fields_and_determinism():
    ix = ix_of(py("auth/service.py", ("class", "AuthService", 12)))
    answer = definitions(ix, "AuthService")
    assert (answer.question, answer.target, answer.options) == ("definitions", None, {"limit": None, "name": "AuthService"})
    assert dumps(answer) == dumps(definitions(ix, "AuthService"))
    assert render_text(answer).splitlines()[:2] == [
        f"definitions AuthService @ {answer.snapshot}",
        "auth/service.py:12  class  AuthService",
    ]


@pytest.mark.parametrize(("name", "limit"), [("", None), ("x", -1)])
def test_bad_arguments(name, limit):
    with pytest.raises(ValueError):
        definitions(ix_of(), name, limit=limit)
