"""Parameters of the graph question routes (specs/018-http-queries research § R2, R3)."""

import pytest

from graphora.api.errors import ApiError
from graphora.api.questions import Question, _allowed, _arguments

ROW = Question("impact", lambda *a, **k: None, "target", ("max_depth", "include_type_only", "follow_barrels", "level"), 50)
DEPENDENTS = Question("dependents", lambda *a, **k: None, "target", ("symbol", "include_type_only", "follow_barrels", "level"), 50)
OVERVIEW = Question("overview", lambda *a, **k: None, None, (), None)
DEFINITIONS = Question("definitions", lambda *a, **k: None, "name", (), 50)


def bad(row, **params):
    with pytest.raises(ApiError) as exc:
        _arguments(row, params)
    assert exc.value.kind == "bad_request" and exc.value.status == 400
    return exc.value.message


def test_allowed():
    assert _allowed(ROW) == (
        ("repository", "snapshot", "target"),
        ("max_depth", "include_type_only", "follow_barrels", "level", "limit"),
    )
    assert _allowed(OVERVIEW) == (("repository", "snapshot"), ())
    assert _allowed(DEFINITIONS) == (("repository", "snapshot", "name"), ("limit",))


def test_defaults():
    assert _arguments(ROW, {"target": "a.py"}) == (
        ("a.py",),
        {"max_depth": None, "include_type_only": True, "follow_barrels": False, "level": "file", "limit": 50},
    )
    assert _arguments(DEPENDENTS, {"target": "a.py"})[1]["symbol"] is None
    assert _arguments(OVERVIEW, {}) == ((), {})
    assert _arguments(DEFINITIONS, {"name": "User"}) == (("User",), {"limit": 50})


def test_values():
    params = {"target": "a.py", "max_depth": "2", "include_type_only": "false", "follow_barrels": "true", "level": "project", "limit": "0"}
    assert _arguments(ROW, params)[1] == {"max_depth": 2, "include_type_only": False, "follow_barrels": True, "level": "project", "limit": 0}
    assert _arguments(ROW, {"target": "a.py", "limit": "500"})[1]["limit"] == 500
    assert _arguments(DEPENDENTS, {"target": "a.py", "symbol": "User"})[1]["symbol"] == "User"


@pytest.mark.parametrize("value", ["1", "yes", "True", ""])
def test_booleans(value):
    assert "include_type_only must be true or false" == bad(ROW, target="a.py", include_type_only=value)


@pytest.mark.parametrize("value", ["x", "1.5", "9999999999", ""])
def test_integers(value):
    assert bad(ROW, target="a.py", max_depth=value) == "max_depth must be an integer"
    assert bad(ROW, target="a.py", limit=value) == "limit must be an integer"


@pytest.mark.parametrize("value", ["-1", "501"])
def test_limit_range(value):
    assert bad(ROW, target="a.py", limit=value) == "limit must be between 0 and 500"


def test_level():
    assert bad(ROW, target="a.py", level="module") == "level must be file or project"
