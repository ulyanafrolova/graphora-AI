"""Barrel following on synthetic documents (specs/004-graph-queries spec US4, research § R8)."""

from graphora.graph.model import Definition, Export, FileNode
from graphora.graph.queries import dependents, impact, index
from synthetic import edge, make_doc


def ts(path, defines=(), exports=()):
    """A TS file node defining (and exporting under the same name) `defines`, and exporting `exports` without a
    definition."""
    definitions = tuple(Definition("function", name, 1, (name,)) for name in defines)
    return FileNode(path, "typescript", definitions, tuple(Export(name, name, 1) for name in exports))


def reexport(source, target, line, symbol, alias=None):
    return edge(source, target, line, symbol=symbol, alias=alias, type="reexports")


def follow(doc, target, **options):
    answer = dependents(index(doc), target, follow_barrels=True, **options)
    return {i.node.removeprefix("file:"): i for i in answer.items}


def steps(item):
    (link,) = item.chain
    return [f"{e.source.removeprefix('file:')}:{e.line}" for e in link.edges + link.via]


def _scenario_one():
    return make_doc(
        [edge("app.ts", "index.ts", 1, symbol="Button"), reexport("index.ts", "Button.tsx", 3, "Button")],
        nodes=[ts("Button.tsx", defines=["Button"])],
    )


def test_import_through_a_barrel():
    items = follow(_scenario_one(), "Button.tsx")
    assert sorted(items) == ["app.ts", "index.ts"]
    assert steps(items["app.ts"]) == ["app.ts:1", "index.ts:3"]
    assert items["app.ts"].chain[0].target == "file:Button.tsx"
    assert [i.node for i in dependents(index(_scenario_one()), "Button.tsx").items] == ["file:index.ts"]


def test_export_star_through_two_barrels():
    doc = make_doc(
        [edge("app.ts", "index.ts", symbol="Card"), reexport("index.ts", "more.ts", 2, "*"), reexport("more.ts", "Card.tsx", 1, "*")],
        nodes=[ts("Card.tsx", defines=["Card"])],
    )
    assert steps(follow(doc, "Card.tsx")["app.ts"]) == ["app.ts:1", "index.ts:2", "more.ts:1"]


def test_untraceable_name_stays_on_the_barrel():
    doc = make_doc(
        [edge("app.ts", "index.ts", symbol="Missing"), reexport("index.ts", "Card.tsx", 1, "*")],
        nodes=[ts("Card.tsx", defines=["Card"])],
    )
    assert "app.ts" not in follow(doc, "Card.tsx")
    assert "app.ts" in follow(doc, "index.ts")


def test_renamed_reexport():
    doc = make_doc(
        [edge("app.ts", "index.ts", symbol="Logger"), reexport("index.ts", "log.ts", 1, "Log", alias="Logger")],
        nodes=[ts("log.ts", defines=["Log"])],
    )
    assert steps(follow(doc, "log.ts")["app.ts"]) == ["app.ts:1", "index.ts:1"]


def test_name_defined_in_the_barrel_stops_there():
    doc = make_doc(
        [edge("app.ts", "index.ts", symbol="Button"), reexport("index.ts", "Button.tsx", 1, "*")],
        nodes=[ts("index.ts", exports=["Button"]), ts("Button.tsx", defines=["Button"])],
    )
    assert "app.ts" not in follow(doc, "Button.tsx")


def test_reexport_loop_stops():
    doc = make_doc(
        [edge("app.ts", "a.ts", symbol="X"), reexport("a.ts", "b.ts", 1, "*"), reexport("b.ts", "a.ts", 1, "*")],
    )
    assert sorted(follow(doc, "a.ts")) == ["app.ts", "b.ts"]
    assert sorted(follow(doc, "b.ts")) == ["a.ts"]


def py(path, defines=()):
    return FileNode(path, "python", tuple(Definition("function", name, 1) for name in defines))


def _package():
    """app.py imports names from pkg/__init__.py, which imports them from its modules (specs/017 research § R3)."""
    return make_doc(
        [
            edge("app.py", "pkg/__init__.py", 1, symbol="AuthService"),
            edge("app.py", "pkg/__init__.py", 2, symbol="tool"),
            edge("app.py", "pkg/__init__.py", 3, symbol="LIMIT"),
            edge("app.py", "pkg/__init__.py", 4, symbol="version"),
            edge("app.py", "pkg/__init__.py", 5, symbol="nothing"),
            edge("pkg/__init__.py", "pkg/auth/__init__.py", 1, symbol="AuthService"),
            edge("pkg/__init__.py", "pkg/tools.py", 2, symbol="*"),
            edge("pkg/__init__.py", "pkg/config.py", 3, symbol="LIMIT"),
            edge("pkg/__init__.py", "unresolved:python:pkg.missing", 4, symbol="nothing"),
            edge("pkg/__init__.py", "pkg/version.py", 5, symbol="version"),
            edge("pkg/auth/__init__.py", "pkg/auth/service.py", 1, symbol="AuthService"),
        ],
        nodes=[py("pkg/__init__.py", ["version"]), py("pkg/auth/service.py", ["AuthService"]), py("pkg/tools.py", ["tool"]), py("pkg/version.py", ["version"])],
    )


def test_python_chain_through_two_packages():
    items = follow(_package(), "pkg/auth/service.py")
    assert sorted(items) == ["app.py", "pkg/__init__.py", "pkg/auth/__init__.py"]
    assert steps(items["app.py"]) == ["app.py:1", "pkg/__init__.py:1", "pkg/auth/__init__.py:1"]
    assert steps(items["pkg/__init__.py"]) == ["pkg/__init__.py:1", "pkg/auth/__init__.py:1"]
    assert items["app.py"].confidence == "resolved"


def test_python_barrels_off_unchanged():
    answer = dependents(index(_package()), "pkg/auth/service.py")
    assert [i.node for i in answer.items] == ["file:pkg/auth/__init__.py"]


def test_python_star_import_is_not_followed():
    assert "app.py" not in follow(_package(), "pkg/tools.py")


def test_python_constant_stops_at_the_imported_file():
    assert steps(follow(_package(), "pkg/config.py")["app.py"]) == ["app.py:3", "pkg/__init__.py:3"]


def test_python_definition_in_the_package_wins():
    assert "app.py" not in follow(_package(), "pkg/version.py")


def test_python_unresolved_import_is_not_followed():
    assert sorted(follow(_package(), "pkg/__init__.py")) == ["app.py"]


def test_python_symbol_filter():
    assert sorted(follow(_package(), "pkg/auth/service.py", symbol="AuthService")) == ["app.py", "pkg/__init__.py", "pkg/auth/__init__.py"]
    assert sorted(follow(_package(), "pkg/auth/service.py", symbol="LIMIT")) == []


def test_python_renamed_import():
    doc = make_doc(
        [
            edge("cli.py", "pkg/__init__.py", 1, symbol="make_server"),
            edge("old.py", "pkg/__init__.py", 1, symbol="create_server"),
            edge("pkg/__init__.py", "pkg/server.py", 2, symbol="create_server", alias="make_server"),
        ],
        nodes=[py("pkg/server.py", ["create_server"])],
    )
    items = follow(doc, "pkg/server.py")
    assert sorted(items) == ["cli.py", "pkg/__init__.py"]
    assert steps(items["cli.py"]) == ["cli.py:1", "pkg/__init__.py:2"]


def test_python_name_imported_twice_under_two_names():
    doc = make_doc(
        [
            edge("a.py", "pkg/__init__.py", 1, symbol="f"),
            edge("b.py", "pkg/__init__.py", 1, symbol="g"),
            edge("pkg/__init__.py", "pkg/x.py", 1, symbol="f"),
            edge("pkg/__init__.py", "pkg/x.py", 1, symbol="f", alias="g"),
        ],
        nodes=[py("pkg/x.py", ["f"])],
    )
    assert sorted(follow(doc, "pkg/x.py")) == ["a.py", "b.py", "pkg/__init__.py"]


def test_python_reimport_through_an_ordinary_module():
    doc = make_doc([edge("c.py", "a.py", 1, symbol="helper"), edge("a.py", "b.py", 1, symbol="helper")], nodes=[py("b.py", ["helper"])])
    assert steps(follow(doc, "b.py")["c.py"]) == ["c.py:1", "a.py:1"]


def test_python_module_imported_as_a_name():
    doc = make_doc([edge("app.py", "pkg/__init__.py", 1, symbol="z"), edge("pkg/__init__.py", "x/y.py", 1, alias="z")])
    assert steps(follow(doc, "x/y.py")["app.py"]) == ["app.py:1", "pkg/__init__.py:1"]


def test_python_loop_of_packages_stops():
    doc = make_doc(
        [edge("app.py", "a/__init__.py", 1, symbol="X"), edge("a/__init__.py", "b/__init__.py", 1, symbol="X"), edge("b/__init__.py", "a/__init__.py", 1, symbol="X")]
    )
    assert sorted(follow(doc, "b/__init__.py")) == ["a/__init__.py"]


def test_symbol_filter_applies_at_the_import_edge():
    doc = make_doc(
        [edge("app.ts", "index.ts", symbol="Logger"), reexport("index.ts", "log.ts", 1, "Log", alias="Logger")],
        nodes=[ts("log.ts", defines=["Log"])],
    )
    assert "app.ts" in follow(doc, "log.ts", symbol="Logger")
    assert "app.ts" not in follow(doc, "log.ts", symbol="Log")


def test_impact_through_barrels():
    doc = make_doc(
        [edge("app.ts", "index.ts", symbol="Button"), reexport("index.ts", "Button.tsx", 3, "Button"), edge("main.ts", "app.ts", 2)],
        nodes=[ts("Button.tsx", defines=["Button"])],
    )
    answer = impact(index(doc), "Button.tsx", follow_barrels=True)
    assert [(i.node, i.distance) for i in answer.items] == [("file:app.ts", 1), ("file:index.ts", 1), ("file:main.ts", 2)]
    main = answer.items[2]
    assert [link.target for link in main.chain] == ["file:app.ts", "file:Button.tsx"]
    assert answer.options["follow_barrels"] is True
