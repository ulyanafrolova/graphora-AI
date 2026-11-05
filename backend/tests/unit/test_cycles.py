"""Cycles on synthetic documents (specs/004-graph-queries spec US2, research § R6)."""

import pytest

from graphora.graph.queries import cycles, index
from synthetic import edge, make_doc


def walk(group):
    return [f"{link.source.removeprefix('file:')}:{link.edges[0].line}" for link in group.cycle]


def test_three_file_loop():
    ix = index(make_doc([edge("a.py", "b.py", 1), edge("b.py", "c.py", 2), edge("c.py", "a.py", 4), edge("d.py", "a.py")]))
    (group,) = cycles(ix).groups
    assert group.files == ("file:a.py", "file:b.py", "file:c.py")
    assert walk(group) == ["a.py:1", "b.py:2", "c.py:4"]
    assert group.cycle[-1].target == "file:a.py"
    assert (group.type_only, group.confidence) == (False, "resolved")


def test_no_cycles_is_an_empty_list():
    answer = cycles(index(make_doc([edge("a.py", "b.py"), edge("b.py", "c.py")])))
    assert (answer.groups, answer.total, answer.truncated) == ((), 0, False)


def test_two_loops_in_a_fixed_order():
    loops = [edge("y.py", "x.py"), edge("x.py", "y.py"), edge("b.py", "a.py"), edge("a.py", "b.py")]
    for edges in (loops, list(reversed(loops))):
        answer = cycles(index(make_doc(edges)))
        assert [g.files for g in answer.groups] == [("file:a.py", "file:b.py"), ("file:x.py", "file:y.py")]


def test_self_import():
    ix = index(make_doc([edge("s.py", "s.py", 3), edge("t.py", "s.py")]))
    (group,) = cycles(ix).groups
    assert (group.files, walk(group)) == (("file:s.py",), ["s.py:3"])


def test_example_cycle_is_the_shortest_through_the_first_file():
    # a → b → c → a and a → d → a: the two-file cycle is shorter
    ix = index(make_doc([edge("a.py", "b.py"), edge("b.py", "c.py"), edge("c.py", "a.py"), edge("a.py", "d.py", 2), edge("d.py", "a.py")]))
    (group,) = cycles(ix).groups
    assert group.files == ("file:a.py", "file:b.py", "file:c.py", "file:d.py")
    assert walk(group) == ["a.py:2", "d.py:1"]


@pytest.mark.parametrize("order", [0, 1])
def test_fixed_choice_between_equally_short_cycles(order):
    edges = [edge("a.py", "c.py", 2), edge("a.py", "b.py", 1), edge("c.py", "a.py"), edge("b.py", "a.py")]
    ix = index(make_doc(edges if order else list(reversed(edges))))
    assert walk(cycles(ix).groups[0]) == ["a.py:1", "b.py:1"]


def test_type_only_loop():
    ix = index(make_doc([edge("a.ts", "b.ts", type_only=True), edge("b.ts", "a.ts")]))
    (group,) = cycles(ix).groups
    assert group.type_only is True
    assert cycles(ix, include_type_only=False).groups == ()


def test_group_with_a_run_time_loop_is_not_type_only():
    # a ↔ b at run time; c joins the group only through a type-only import
    ix = index(make_doc([edge("a.ts", "b.ts"), edge("b.ts", "a.ts"), edge("b.ts", "c.ts", type_only=True), edge("c.ts", "a.ts")]))
    (group,) = cycles(ix).groups
    assert group.files == ("file:a.ts", "file:b.ts", "file:c.ts")
    assert group.type_only is False


def test_heuristic_link_in_the_cycle():
    ix = index(make_doc([edge("a.py", "b.py", confidence="heuristic"), edge("b.py", "a.py")]))
    assert cycles(ix).groups[0].confidence == "heuristic"


def test_limit_and_no_completeness():
    ix = index(make_doc([edge("a.py", "b.py"), edge("b.py", "a.py"), edge("x.py", "y.py"), edge("y.py", "x.py")]))
    answer = cycles(ix, limit=1)
    assert [g.files[0] for g in answer.groups] == ["file:a.py"]
    assert (answer.total, answer.truncated, answer.completeness, answer.target) == (2, True, None, None)
    assert answer.options == {"include_type_only": True, "limit": 1}
