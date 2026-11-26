"""Route and call facts for the HTTP bridge (specs/015-http-bridge research R2, R3; tasks T010, T011, T020, T025)."""

import pytest

from graphora.adapters.js.extract import extract as js_extract
from graphora.adapters.js.http import Part
from graphora.adapters.python.extract import extract as py_extract


def routes(source):
    return [(r.obj, r.methods, r.path, r.line) for r in py_extract(source.encode()).routes]


def calls(source, path="a.ts"):
    return [(c.method, c.parts, c.absolute, c.line) for c in js_extract(path, source.encode()).http_calls]


T = lambda v: Part("text", v)  # noqa: E731
X = lambda v=None: Part("expr", v)  # noqa: E731


# --- Python routes (US1) ---------------------------------------------------------------------------------


def test_route_decorators():
    source = """\
@app.get("/a")
def a(): pass
@router.post("/a")
def b(): pass
@app.api_route("/a", methods=["POST", "get"])
def c(): pass
@app.route("/a")
def d(): pass
@bp.route("/a", methods=["DELETE"])
def e(): pass
class K:
    @app.put("/k")
    def m(self): pass
"""
    assert routes(source) == [
        ("app", ("GET",), "/a", 1),
        ("router", ("POST",), "/a", 3),
        ("app", ("GET", "POST"), "/a", 5),
        ("app", ("GET",), "/a", 7),
        ("bp", ("DELETE",), "/a", 9),
        ("app", ("PUT",), "/k", 12),
    ]
    fact = py_extract(b'@app.get("/a")\ndef a(): pass\n').routes[0]
    assert (fact.column, fact.text) == (1, '@app.get("/a")')


def test_what_is_not_a_route():
    source = """\
@app.get(path)
def a(): pass
@app.get(f"/x/{y}")
def b(): pass
@cache
def c(): pass
@app.route("/m", methods=verbs)
def d(): pass
# @app.get("/comment")
app.get("/not-a-decorator")
"""
    assert routes(source) == []


# --- JS calls (US1) --------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["a.ts", "a.tsx", "a.js", "a.jsx"])
def test_call_forms(path):
    source = """\
fetch("/a");
fetch("/a", { method: "POST" });
window.fetch("/a");
globalThis.fetch("/a");
axios.get("/a");
axios.delete('/a');
axios({ url: "/a", method: "put" });
axios.request({ url: "/a", method: "patch" });
fetch("/a", { method: m });
getUser("/a");
client.get("/a");
"""
    assert calls(source, path) == [
        ("GET", (T("/a"),), False, 1),
        ("POST", (T("/a"),), False, 2),
        ("GET", (T("/a"),), False, 3),
        ("GET", (T("/a"),), False, 4),
        ("GET", (T("/a"),), False, 5),
        ("DELETE", (T("/a"),), False, 6),
        ("PUT", (T("/a"),), False, 7),
        ("PATCH", (T("/a"),), False, 8),
        (None, (T("/a"),), False, 9),
    ]


# --- parameters (US2) ------------------------------------------------------------------------------------


def test_templates_and_concatenation():
    source = """\
fetch(`/users/${id}`);
fetch("/users/" + id + "/orders");
fetch(`/plain`);
fetch(url);
fetch(buildUrl());
fetch("https://api.github.com/x");
fetch("//cdn.example/y");
"""
    assert calls(source) == [
        ("GET", (T("/users/"), X("id")), False, 1),
        ("GET", (T("/users/"), X("id"), T("/orders")), False, 2),
        ("GET", (T("/plain"),), False, 3),
        ("GET", (X("url"),), False, 4),  # a name: substituted if it is a top-level constant, else dynamic
        ("GET", None, False, 5),
        ("GET", (T("https://api.github.com/x"),), True, 6),
        ("GET", (T("//cdn.example/y"),), True, 7),
    ]


# --- prefixes and constants (US3) ------------------------------------------------------------------------


def test_routers_and_mounts():
    source = """\
from fastapi import APIRouter, FastAPI
from flask import Blueprint, Flask
app = FastAPI()
router = APIRouter(prefix="/api")
plain = APIRouter()
bp = Blueprint("b", __name__, url_prefix="/b")
dyn = APIRouter(prefix=PREFIX)
flask_app = Flask(__name__)
app.include_router(items.router, prefix="/v1")
app.include_router(router)
flask_app.register_blueprint(bp, url_prefix="/x")
app.include_router(router, prefix=settings.P)
"""
    facts = py_extract(source.encode())
    assert [(r.name, r.kind, r.prefix) for r in facts.routers] == [
        ("app", "app", ""), ("router", "router", "/api"), ("plain", "router", ""), ("bp", "blueprint", "/b"),
        ("dyn", "router", None), ("flask_app", "app", ""),
    ]
    assert [(m.app, m.target, m.prefix, m.given) for m in facts.mounts] == [
        ("app", "items.router", "/v1", True), ("app", "router", "", False), ("flask_app", "bp", "/x", True),
        ("app", "router", None, True),
    ]


def test_top_level_string_constants_only():
    source = """\
const API = "/api";
export const V2 = '/v2';
let L = "/l";
const T = `/t/${x}`;
function f() { const INNER = "/inner"; }
"""
    assert js_extract("a.ts", source.encode()).constants == {"API": "/api", "V2": "/v2"}


def test_a_url_inside_the_query_is_not_another_host():
    """Only a scheme or `//` at the start means another host (013 review)."""
    assert calls('fetch("/api/proxy?u=https://x.com");') == [("GET", (T("/api/proxy?u=https://x.com"),), False, 1)]
    assert calls('fetch("HTTPS://x.com/a");')[0][2] is True


def test_options_that_are_not_a_literal_leave_the_method_unknown():
    """A variable or a spread in the options may set any method (013 review)."""
    source = """\
fetch("/a", opts);
fetch("/a", { ...opts });
fetch("/a", { method: "PUT", ...opts });
fetch("/a", { ...opts, method: "PUT" });
fetch("/a", { headers: h });
axios("/a", config);
axios.request(config);
"""
    assert [c[0] for c in calls(source)] == [None, None, None, "PUT", "GET", None, None]


def test_empty_method_strings_make_no_route():
    assert routes('@app.route("/x", methods=[""])\ndef x(): pass\n') == []
