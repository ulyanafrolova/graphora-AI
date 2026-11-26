"""Routes, prefixes and matching of the HTTP bridge (specs/015-http-bridge research R2–R5; tasks T012, T021,
T026, T031)."""

from graphora.adapters.js.extract import extract as js_extract
from graphora.adapters.python.extract import extract as py_extract
from graphora.resolve.http import Call, Route, bridge, match, routes

SNAP = "content:0123456789abcdef"


def py(**files):
    return {path.replace("__", "/") + ".py": py_extract(text.encode()) for path, text in files.items()}


def call(segments, method="GET"):
    return Call("f.ts", method, segments, 1, 1, "fetch()")


R = lambda file, segments, methods=("GET",), line=1: Route(file, methods, segments, line)  # noqa: E731


# --- US1: literal match ----------------------------------------------------------------------------------


def test_method_and_path():
    items = R("backend/app/items.py", ("api", "items"), ("GET",), 8)
    assert match(call(("api", "items")), [items]) == ("edge", items)
    assert match(call(("api", "items"), "POST"), [items]) == ("not_found", None)
    both = R("b.py", ("api", "items"), ("GET", "POST"))
    assert match(call(("api", "items"), "POST"), [both]) == ("edge", both)


# --- US2: parameters -------------------------------------------------------------------------------------


def test_literal_and_parameter_routes():
    me, by_id, orders = R("a.py", ("users", "me"), line=5), R("a.py", ("users", "*"), line=7), R("a.py", ("users", "*", "orders"), line=9)
    two = [me, by_id]
    assert match(call(("users", "me")), two) == ("edge", me)
    assert match(call(("users", "*")), two) == ("edge", by_id)
    assert match(call(("users", "1")), two) == ("edge", by_id)
    assert match(call(("users", "1", "orders")), [orders]) == ("edge", orders)
    assert match(call(("users", "1", "orders")), two) == ("not_found", None)


# --- US3: prefixes ---------------------------------------------------------------------------------------


def test_fastapi_prefixes_compose_through_imports():
    facts = py(
        backend____init__="",
        backend__app____init__="",
        backend__app__routers____init__="",
        backend__app__routers__items="""\
from fastapi import APIRouter
router = APIRouter(prefix="/orders")
@router.get("/{order_id}")
def o(): pass
""",
        backend__app__main="""\
from fastapi import FastAPI
from backend.app.routers import items
app = FastAPI()
app.include_router(items.router, prefix="/v1")
app.include_router(items.router, prefix="/v2")
""",
    )
    assert [(r.file, r.segments) for r in routes(facts)] == [
        ("backend/app/routers/items.py", ("v1", "orders", "*")),
        ("backend/app/routers/items.py", ("v2", "orders", "*")),
    ]


def test_flask_url_prefix_replaces_the_blueprint_prefix():
    facts = py(
        bp="""\
from flask import Blueprint
a = Blueprint("a", __name__, url_prefix="/b")
@a.route("/x")
def x(): pass
c = Blueprint("c", __name__, url_prefix="/c")
@c.route("/y")
def y(): pass
""",
        app="""\
from flask import Flask
from bp import a, c
app = Flask(__name__)
app.register_blueprint(a, url_prefix="/x")
app.register_blueprint(c)
""",
    )
    assert sorted(r.segments for r in routes(facts)) == [("c", "y"), ("x", "x")]


def test_unknown_prefix_matches_nothing_and_unmounted_router_keeps_its_own():
    facts = py(
        main="""\
from fastapi import APIRouter, FastAPI
app = FastAPI()
dyn = APIRouter(prefix=PREFIX)
@dyn.get("/a")
def a(): pass
mounted = APIRouter(prefix="/m")
@mounted.get("/b")
def b(): pass
app.include_router(mounted, prefix=settings.P)
lonely = APIRouter(prefix="/l")
@lonely.get("/c")
def c(): pass
@unknown_object.get("/d")
def d(): pass
""",
    )
    assert [r.segments for r in routes(facts)] == [("l", "c")]


def test_base_constant_in_the_calling_file():
    facts = py(main='from fastapi import FastAPI\napp = FastAPI()\n@app.get("/api/items")\ndef a(): pass\n')
    js = {
        "f/a.ts": js_extract("f/a.ts", b'const API = "/api";\nfetch(`${API}/items`);\nfetch(`${OTHER}/items`);\n'),
    }
    edges, _ = bridge(facts, js, SNAP)
    assert [(e.line, e.confidence, e.reason) for e in edges] == [(2, "heuristic", "http_route"), (3, "unresolved", "dynamic")]


# --- US4: unresolved -------------------------------------------------------------------------------------


def test_unresolved_reasons_and_other_hosts():
    facts = py(
        a='from fastapi import FastAPI\napp = FastAPI()\n@app.get("/health")\ndef h(): pass\n@app.get("/api/items")\ndef i(): pass\n',
        b='from fastapi import FastAPI\napp = FastAPI()\n@app.get("/health")\ndef h(): pass\n',
    )
    source = b"""\
fetch(url);
fetch("/nowhere");
fetch("/health");
fetch("/api/items", { method: m });
fetch("https://api.github.com/x");
fetch("//cdn.example/y");
"""
    edges, nodes = bridge(facts, {"f.ts": js_extract("f.ts", source)}, SNAP)
    assert [(e.line, e.target, e.confidence, e.reason, e.route_line) for e in edges] == [
        (1, "unresolved:http:GET ?", "unresolved", "dynamic", None),
        (2, "unresolved:http:GET /nowhere", "unresolved", "not_found", None),
        (3, "unresolved:http:GET /health", "unresolved", "ambiguous", None),
        (4, "file:a.py", "heuristic", "http_route", 5),
    ]
    assert all(e.type == "http_call" and e.extractor.startswith("http-bridge@") for e in edges)
    assert [(n.id, n.ecosystem) for n in nodes] == [
        ("unresolved:http:GET /health", "http"), ("unresolved:http:GET /nowhere", "http"), ("unresolved:http:GET ?", "http"),
    ]


def test_unknown_method_in_two_files_is_ambiguous():
    routes_ = [R("a.py", ("api", "items"), ("GET",)), R("b.py", ("api", "items"), ("POST",))]
    assert match(call(("api", "items"), None), routes_) == ("ambiguous", None)
    assert match(call(("api", "items"), None), routes_[:1]) == ("edge", routes_[0])


ORDERS = """\
from fastapi import APIRouter
router = APIRouter(prefix="/orders")
@router.get("/x")
def x(): pass
"""


def test_relative_imports_of_a_router_module():
    """`from .routers import orders` and `from . import orders` bind the module (013 review, FastAPI tutorial layout)."""
    for main in ("from .routers import orders\n", "from . import routers\nfrom .routers import orders\n"):
        facts = py(app____init__="", app__routers____init__="", app__routers__orders=ORDERS, app__main=(
            "from fastapi import FastAPI\n" + main + 'app = FastAPI()\napp.include_router(orders.router, prefix="/v1")\n'))
        assert [r.segments for r in routes(facts)] == [("v1", "orders", "x")]
    facts = py(app____init__="", app__routers____init__="", app__routers__orders=ORDERS, app__routers__main=(
        'from fastapi import FastAPI\nfrom . import orders\napp = FastAPI()\napp.include_router(orders.router, prefix="/v1")\n'))
    assert [r.segments for r in routes(facts)] == [("v1", "orders", "x")]


def test_a_mount_that_cannot_be_followed_makes_the_prefix_unknown():
    """An app made in a factory function: its blueprint's served path is unknown, never its own prefix (013 review)."""
    facts = py(
        bp='from flask import Blueprint\nbp = Blueprint("b", __name__)\n@bp.route("/x")\ndef x(): pass\n',
        app='from flask import Flask\nfrom bp import bp\ndef create_app():\n    app = Flask(__name__)\n    app.register_blueprint(bp, url_prefix="/api")\n',
    )
    assert routes(facts) == []


def test_router_passed_by_keyword():
    facts = py(m='from fastapi import APIRouter, FastAPI\napp = FastAPI()\nr = APIRouter()\n@r.get("/x")\ndef x(): pass\n'
                 'app.include_router(router=r, prefix="/v1")\n')
    assert [r.segments for r in routes(facts)] == [("v1", "x")]


def test_plain_dotted_import_is_reached_by_its_full_name():
    """`import app.routers.orders` binds `app`, not orders.py; the mount uses the full dotted path (013 review)."""
    base = dict(app____init__="", app__routers____init__="", app__routers__orders=ORDERS)
    full = py(**base, main='from fastapi import FastAPI\nimport app.routers.orders\napi = FastAPI()\n'
                          'api.include_router(app.routers.orders.router, prefix="/v1")\n')
    assert [r.segments for r in routes(full)] == [("v1", "orders", "x")]
    aliased = py(**base, main='from fastapi import FastAPI\nimport app.routers.orders as o\napi = FastAPI()\n'
                             'api.include_router(o.router, prefix="/v2")\n')
    assert [r.segments for r in routes(aliased)] == [("v2", "orders", "x")]
    wrong = py(**base, main='from fastapi import FastAPI\nimport app.routers.orders\napi = FastAPI()\n'
                           'api.include_router(app.router, prefix="/v3")\n')
    assert [r.segments for r in routes(wrong)] == [("orders", "x")]
