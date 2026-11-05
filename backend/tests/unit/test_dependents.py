"""Dependencies, dependents and impact on synthetic documents (specs/004-graph-queries spec US1, research § R4, R5)."""

import pytest

from graphora.graph.queries import dependencies, dependents, impact, index
from graphora.graph.results import dumps
from synthetic import SNAP, edge, make_doc


def chain(item):
    return [f"{link.source.removeprefix('file:')}:{link.edges[0].line}" for link in item.chain]


def nodes(answer):
    return [i.node for i in answer.items]


# --- dependents ---------------------------------------------------------------------------------------------


def test_direct_dependent_with_its_edge():
    e = edge("api/routes.py", "auth/service.py", 3, symbol="AuthService")
    answer = dependents(index(make_doc([e])), "auth/service.py")
    (item,) = answer.items
    assert item.node == "file:api/routes.py"
    assert item.chain[0].edges == (e,)
    assert (item.confidence, answer.snapshot, answer.target) == ("resolved", SNAP, "file:auth/service.py")


def test_two_import_lines_are_one_item_with_both_edges():
    e1, e2 = edge("b.py", "a.py", 1), edge("b.py", "a.py", 4)
    (item,) = dependents(index(make_doc([e2, e1])), "a.py").items
    assert item.chain[0].edges == (e1, e2)


def test_dependents_of_an_external_package():
    ix = index(make_doc([edge("b.py", "ext:python:lodash", 2), edge("a.py", "ext:python:lodash", 5), edge("a.py", "c.py")]))
    answer = dependents(ix, "lodash")
    assert nodes(answer) == ["file:a.py", "file:b.py"]
    assert [chain(i) for i in answer.items] == [["a.py:5"], ["b.py:2"]]


def test_type_only_dependent():
    ix = index(make_doc([edge("t.ts", "a.ts", type_only=True), edge("r.ts", "a.ts")]))
    answer = dependents(ix, "a.ts")
    assert [(i.node, i.type_only) for i in answer.items] == [("file:r.ts", False), ("file:t.ts", True)]
    assert nodes(dependents(ix, "a.ts", include_type_only=False)) == ["file:r.ts"]


def test_symbol_filter_keeps_only_matching_edges():
    keep = edge("b.py", "a.py", 2, symbol="AuthService")
    ix = index(make_doc([edge("b.py", "a.py", 1, symbol="other"), keep, edge("c.py", "a.py", symbol="other")]))
    (item,) = dependents(ix, "a.py", symbol="AuthService").items
    assert item.node == "file:b.py"
    assert item.chain[0].edges == (keep,)


def test_symbol_filter_matches_reexport_alias():
    e = edge("index.ts", "log.ts", symbol="Log", alias="Logger", type="reexports")
    ix = index(make_doc([e]))
    assert nodes(dependents(ix, "log.ts", symbol="Logger")) == ["file:index.ts"]


def test_follow_barrels_not_yet():
    with pytest.raises(NotImplementedError):
        dependents(index(make_doc([edge("b.py", "a.py")])), "a.py", follow_barrels=True)


# --- confidence ---------------------------------------------------------------------------------------------


def test_heuristic_chain():
    ix = index(make_doc([edge("b.py", "a.py", confidence="heuristic"), edge("c.py", "b.py")]))
    answer = impact(ix, "a.py")
    assert [(i.node, i.confidence) for i in answer.items] == [("file:b.py", "heuristic"), ("file:c.py", "heuristic")]


def test_one_resolved_edge_makes_the_link_resolved():
    ix = index(make_doc([edge("b.py", "a.py", 1, confidence="heuristic"), edge("b.py", "a.py", 2)]))
    (item,) = dependents(ix, "a.py").items
    assert item.confidence == "resolved"


# --- impact -------------------------------------------------------------------------------------------------


def _line():
    return index(make_doc([edge("c.py", "b.py", 4), edge("b.py", "a.py", 2)]))


def test_impact_distances_and_chain():
    answer = impact(_line(), "a.py")
    assert [(i.node, i.distance, chain(i)) for i in answer.items] == [
        ("file:b.py", 1, ["b.py:2"]),
        ("file:c.py", 2, ["c.py:4", "b.py:2"]),
    ]
    assert answer.cut is False


def test_impact_max_depth_cuts():
    answer = impact(_line(), "a.py", max_depth=1)
    assert nodes(answer) == ["file:b.py"]
    assert answer.cut is True
    assert answer.options["max_depth"] == 1


def test_impact_not_cut_when_nothing_lies_beyond():
    assert impact(_line(), "a.py", max_depth=2).cut is False


@pytest.mark.parametrize("order", [0, 1])
def test_impact_chain_goes_through_the_smallest_id(order):
    edges = [edge("d.py", "b2.py"), edge("d.py", "b1.py"), edge("b1.py", "a.py"), edge("b2.py", "a.py")]
    ix = index(make_doc(edges if order else list(reversed(edges))))
    d = next(i for i in impact(ix, "a.py").items if i.node == "file:d.py")
    assert [link.target for link in d.chain] == ["file:b1.py", "file:a.py"]


def test_impact_of_external_package_and_no_passing_through_externals():
    ix = index(make_doc([edge("b.py", "ext:python:yaml"), edge("c.py", "b.py"), edge("b.py", "asset:x.css")]))
    assert [(i.node, i.distance) for i in impact(ix, "yaml").items] == [("file:b.py", 1), ("file:c.py", 2)]
    assert impact(ix, "asset:x.css").items[0].node == "file:b.py"


def test_impact_type_only():
    ix = index(make_doc([edge("b.ts", "a.ts", type_only=True), edge("c.ts", "b.ts")]))
    assert [(i.node, i.type_only) for i in impact(ix, "a.ts").items] == [("file:b.ts", True), ("file:c.ts", True)]
    assert impact(ix, "a.ts", include_type_only=False).items == ()


# --- dependencies -------------------------------------------------------------------------------------------


def test_dependencies_grouped_by_target_with_unresolved_apart():
    u = edge("a.py", "unresolved:python:x", 9)
    ix = index(make_doc([edge("a.py", "z.py", 1), edge("a.py", "ext:python:os", 3), edge("a.py", "b.py", 2), edge("a.py", "b.py", 5), u]))
    answer = dependencies(ix, "a.py")
    assert nodes(answer) == ["ext:python:os", "file:b.py", "file:z.py"]
    assert [len(i.chain[0].edges) for i in answer.items] == [1, 2, 1]
    assert answer.items[0].kind == "external"
    assert answer.unresolved == (u,)


# --- limits and common fields -------------------------------------------------------------------------------


def _fan():
    return index(make_doc([edge(f"d{n}.py", "a.py") for n in range(5)]))


def test_limit():
    answer = dependents(_fan(), "a.py", limit=2)
    assert nodes(answer) == ["file:d0.py", "file:d1.py"]
    assert (answer.total, answer.truncated) == (5, True)
    zero = dependents(_fan(), "a.py", limit=0)
    assert (zero.items, zero.total, zero.truncated) == ((), 5, True)
    assert dependents(_fan(), "a.py", limit=5).truncated is False


@pytest.mark.parametrize("call", [
    lambda ix: dependents(ix, "a.py", limit=-1),
    lambda ix: impact(ix, "a.py", max_depth=0),
    lambda ix: dependencies(ix, "d0.py", limit=-1),
])
def test_bad_option_values(call):
    with pytest.raises(ValueError):
        call(_fan())


def test_answers_echo_options_and_completeness():
    ix = index(make_doc([edge("b.py", "a.py"), edge("b.py", "unresolved:python:q", 2)]))
    answer = impact(ix, "./a.py")
    assert answer.options == {"follow_barrels": False, "include_type_only": True, "limit": None, "max_depth": None}
    assert answer.question == "impact"
    assert answer.completeness.unresolved_imports == 1
    assert dependents(ix, "a.py").options == {"follow_barrels": False, "include_type_only": True, "limit": None, "symbol": None}
    assert dependencies(ix, "b.py").options == {"include_type_only": True, "limit": None}


def test_same_question_same_bytes():
    ix = _fan()
    assert dumps(impact(ix, "a.py")) == dumps(impact(index(ix.doc), "a.py"))
