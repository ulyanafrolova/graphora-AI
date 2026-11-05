"""Neighbors and key files on synthetic documents (specs/004-graph-queries spec US3, research § R7)."""

from graphora.graph.queries import index, key_files, neighbors
from synthetic import edge, make_doc


def ranked(answer):
    return [(i.node.removeprefix("file:"), i.transitive_dependents, i.direct_dependents) for i in answer.items]


def test_neighbors_both_ways_with_edges():
    to_a, to_os, from_c = edge("b.py", "a.py", 2), edge("b.py", "ext:python:os", 1), edge("c.py", "b.py", 5)
    answer = neighbors(index(make_doc([to_a, to_os, from_c])), "b.py")
    assert [(i.node, i.chain[0].edges) for i in answer.outgoing] == [("ext:python:os", (to_os,)), ("file:a.py", (to_a,))]
    assert [(i.node, i.chain[0].edges) for i in answer.incoming] == [("file:c.py", (from_c,))]
    assert answer.total == 3
    assert answer.items is None


def test_neighbors_unresolved_listed_apart():
    u = edge("b.py", "unresolved:python:gone", 4, reason="not_found")
    answer = neighbors(index(make_doc([u, edge("b.py", "a.py")])), "b.py")
    assert answer.unresolved == (u,)
    assert [i.node for i in answer.outgoing] == ["file:a.py"]


def test_neighbors_limit_cuts_each_list():
    edges = [edge("b.py", f"o{n}.py") for n in range(3)] + [edge(f"i{n}.py", "b.py") for n in range(2)]
    answer = neighbors(index(make_doc(edges)), "b.py", limit=1)
    assert ([i.node for i in answer.outgoing], [i.node for i in answer.incoming]) == (["file:o0.py"], ["file:i0.py"])
    assert (answer.total, answer.truncated) == (5, True)
    assert neighbors(index(make_doc(edges)), "b.py", limit=3).truncated is False


def test_key_files_rank():
    # d → c → a, e → a, b → c: a has 4 transitive dependents (c, d, e, b), c has 2
    ix = index(make_doc([edge("d.py", "c.py"), edge("c.py", "a.py"), edge("e.py", "a.py"), edge("b.py", "c.py")]))
    assert ranked(key_files(ix)) == [("a.py", 4, 2), ("c.py", 2, 2)]


def test_key_files_ties_by_direct_then_path():
    # x and y both have 2 transitive dependents; y has 2 direct, x has 1
    ix = index(make_doc([edge("p.py", "q.py"), edge("q.py", "x.py"), edge("m.py", "y.py"), edge("n.py", "y.py"), edge("s.py", "z.py"), edge("t.py", "w.py")]))
    assert ranked(key_files(ix))[:2] == [("y.py", 2, 2), ("x.py", 2, 1)]
    assert ranked(key_files(ix))[2:] == [("q.py", 1, 1), ("w.py", 1, 1), ("z.py", 1, 1)]


def test_files_in_a_loop_share_their_dependents_but_not_themselves():
    ix = index(make_doc([edge("a.py", "b.py"), edge("b.py", "a.py"), edge("u.py", "a.py"), edge("s.py", "s.py")]))
    assert ranked(key_files(ix)) == [("a.py", 2, 2), ("b.py", 2, 1)]


def test_key_files_only_files_and_default_limit():
    edges = [edge(f"d{n:02}.py", f"t{n:02}.py") for n in range(12)] + [edge("d00.py", "ext:python:os")]
    answer = key_files(index(make_doc(edges)))
    assert len(answer.items) == 10
    assert (answer.total, answer.truncated) == (12, True)
    assert all(i.node.startswith("file:") for i in answer.items)
    assert answer.options == {"include_type_only": True, "limit": 10}


def test_key_files_without_type_only():
    ix = index(make_doc([edge("b.ts", "a.ts", type_only=True), edge("c.ts", "a.ts")]))
    assert ranked(key_files(ix)) == [("a.ts", 2, 2)]
    assert ranked(key_files(ix, include_type_only=False)) == [("a.ts", 1, 1)]
