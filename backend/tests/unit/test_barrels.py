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


def test_python_edges_are_never_followed():
    doc = make_doc([edge("app.py", "pkg/__init__.py", symbol="f"), edge("pkg/__init__.py", "pkg/f.py", symbol="f")])
    assert sorted(follow(doc, "pkg/f.py")) == ["pkg/__init__.py"]


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
