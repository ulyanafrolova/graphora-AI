"""Suggested links to remove in each cycle group (specs/019-frontend research § R4)."""

import json

import networkx as nx

from graphora.graph import queries
from graphora.graph.results import dumps
from test_components import doc, edge


def cuts(d):
    a = json.loads(dumps(queries.cycles(queries.index(d))))
    return [
        (g["suggested_cut"]["method"], [(link["source"][5:], link["target"][5:]) for link in g["suggested_cut"]["links"]])
        for g in a["groups"]
    ]


def test_two_files():
    assert cuts(doc([edge("a.py", "b.py"), edge("b.py", "a.py")])) == [("exact", [("a.py", "b.py")])]


def test_fewest_import_edges_then_path():
    d = doc([edge("a.py", "b.py"), edge("a.py", "b.py", line=2), edge("b.py", "c.py"), edge("c.py", "a.py")])
    assert cuts(d) == [("exact", [("b.py", "c.py")])]


def test_shared_link_breaks_both_loops():
    d = doc([edge("a.py", "b.py"), edge("b.py", "a.py"), edge("b.py", "c.py"), edge("c.py", "a.py")])
    assert cuts(d) == [("exact", [("a.py", "b.py")])]


def test_two_links_needed():
    d = doc([edge("a.py", "b.py"), edge("b.py", "a.py"), edge("c.py", "d.py"), edge("d.py", "c.py"), edge("b.py", "c.py"), edge("d.py", "a.py")])
    method, links = cuts(d)[0]
    assert method == "exact" and len(links) == 2


def test_self_import():
    assert cuts(doc([edge("a.py", "a.py")])) == [("exact", [("a.py", "a.py")])]


def test_large_group_is_greedy():
    names = [f"m{i:02}.py" for i in range(21)]
    d = doc([edge(a, b) for a, b in zip(names, names[1:] + names[:1], strict=True)])
    assert cuts(d) == [("greedy", [("m00.py", "m01.py")])]


def test_budget_falls_back_to_greedy(monkeypatch):
    monkeypatch.setattr(queries, "CUT_BUDGET", 1)
    d = doc([edge("a.py", "b.py"), edge("b.py", "c.py"), edge("c.py", "a.py"), edge("b.py", "a.py")])
    assert cuts(d)[0][0] == "greedy"


def test_removing_the_cut_leaves_no_cycle():
    d = doc(
        [edge("a.py", "b.py"), edge("b.py", "c.py"), edge("c.py", "a.py"), edge("c.py", "b.py"), edge("b.py", "d.py"), edge("d.py", "a.py")]
    )
    for _, links in cuts(d):
        g = nx.DiGraph([(e.source, e.target) for e in d.edges])
        g.remove_edges_from([(f"file:{a}", f"file:{b}") for a, b in links])
        assert nx.is_directed_acyclic_graph(g)


def test_same_bytes_twice():
    d = doc([edge("a.py", "b.py"), edge("b.py", "a.py")])
    assert dumps(queries.cycles(queries.index(d))) == dumps(queries.cycles(queries.index(d)))
