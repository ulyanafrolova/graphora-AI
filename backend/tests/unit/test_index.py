"""The query index and node addressing (specs/004-graph-queries research § R3, R4, R9, R10)."""

import pytest

from graphora.graph.model import CoverageFile, Skipped
from graphora.graph.queries import NodeNotFound, _links, index, resolve
from graphora.graph.serialize import edge_sort_key
from synthetic import SNAP, edge, make_doc


# --- links --------------------------------------------------------------------------------------------------


def test_one_link_per_pair_with_every_edge_sorted():
    e1, e2, e3 = edge("a.py", "b.py", 7), edge("a.py", "b.py", 2), edge("a.py", "b.py", 2, column=9, symbol="x")
    ix = index(make_doc([e1, e2, e3]))
    assert list(ix.links.edges) == [("file:a.py", "file:b.py")]
    assert ix.links.edges["file:a.py", "file:b.py"]["edges"] == tuple(sorted([e1, e2, e3], key=edge_sort_key))


def test_unresolved_edges_never_form_links():
    u2, u1 = edge("a.py", "unresolved:python:y", 5), edge("a.py", "unresolved:python:x", 2)
    ix = index(make_doc([u2, u1, edge("a.py", "b.py")]))
    assert "unresolved:python:x" not in ix.links
    assert list(ix.links.edges) == [("file:a.py", "file:b.py")]
    assert ix.unresolved == {"file:a.py": (u1, u2)}


def test_link_confidence_is_the_strongest_edge():
    ix = index(make_doc([edge("a.py", "b.py", 1, confidence="heuristic"), edge("a.py", "b.py", 2), edge("a.py", "c.py", confidence="heuristic")]))
    assert ix.link("file:a.py", "file:b.py").confidence == "resolved"
    assert ix.link("file:a.py", "file:c.py").confidence == "heuristic"


def test_link_is_type_only_only_when_every_edge_is():
    ix = index(make_doc([edge("a.ts", "b.ts", 1, type_only=True), edge("a.ts", "b.ts", 2), edge("a.ts", "c.ts", type_only=True)]))
    assert ix.link("file:a.ts", "file:b.ts").type_only is False
    assert ix.link("file:a.ts", "file:c.ts").type_only is True


def test_without_type_only_edges():
    keep, drop = edge("a.ts", "b.ts", 2), edge("a.ts", "b.ts", 1, type_only=True)
    ix = index(make_doc([keep, drop, edge("a.ts", "c.ts", type_only=True)]))
    runtime = _links(ix, include_type_only=False)
    assert list(runtime.edges) == [("file:a.ts", "file:b.ts")]
    assert runtime.edges["file:a.ts", "file:b.ts"]["edges"] == (keep,)
    assert _links(ix, include_type_only=False) is runtime
    assert _links(ix, include_type_only=True) is ix.links


# --- completeness -------------------------------------------------------------------------------------------


def test_completeness():
    doc = make_doc(
        [edge("a.py", "unresolved:python:x"), edge("a.py", "unresolved:python:y", 2), edge("a.py", "b.py")],
        coverage=[
            CoverageFile("b.py", "python", "analyzed", ("parse_error",)),
            CoverageFile("c.py", "python", "analyzed", ("unreadable",)),
            CoverageFile("main.go", "go", "detected_only"),
            CoverageFile("README.md", None, "not_code"),
        ],
    )
    c = index(doc).completeness
    assert (c.unresolved_imports, c.not_analyzed_files, c.files_with_errors) == (2, 1, 2)


# --- resolve ------------------------------------------------------------------------------------------------


def _ix():
    return index(
        make_doc(
            [
                edge("src/a.py", "src/b.py"),
                edge("src/a.py", "ext:python:requests"),
                edge("web/x.ts", "ext:npm:react"),
                edge("web/x.ts", "ext:npm:yaml"),
                edge("src/a.py", "ext:python:yaml"),
            ],
            coverage=[CoverageFile("gen/main.go", "go", "detected_only"), CoverageFile("README.md", None, "not_code")],
            skipped=[Skipped("node_modules", "excluded_dir"), Skipped("link.py", "symlink")],
        )
    )


@pytest.mark.parametrize(
    "target, node_id",
    [
        ("file:src/a.py", "file:src/a.py"),
        ("ext:npm:react", "ext:npm:react"),
        ("src/b.py", "file:src/b.py"),
        ("./src/b.py", "file:src/b.py"),
        ("requests", "ext:python:requests"),
        ("react", "ext:npm:react"),
    ],
)
def test_resolve(target, node_id):
    assert resolve(_ix(), target) == node_id


@pytest.mark.parametrize(
    "target, status",
    [
        ("yaml", "ambiguous"),
        ("src\\a.py", "invalid_path"),
        ("/src/a.py", "invalid_path"),
        ("src/../src/a.py", "invalid_path"),
        ("gen/main.go", "detected_only"),
        ("README.md", "not_code"),
        ("node_modules/react/index.js", "excluded_dir"),
        ("link.py", "symlink"),
        ("missing.py", "not_in_snapshot"),
    ],
)
def test_resolve_not_found(target, status):
    with pytest.raises(NodeNotFound) as exc:
        resolve(_ix(), target)
    assert (exc.value.target, exc.value.status) == (target, status)


def test_not_found_messages():
    def message(target):
        with pytest.raises(NodeNotFound) as exc:
            resolve(_ix(), target)
        return exc.value.message

    assert message("gen/main.go") == "gen/main.go is detected_only (not analyzed)"
    assert message("node_modules") == "node_modules is skipped (excluded_dir)"
    assert message("missing.py") == f"missing.py is not in snapshot {SNAP}"
    assert "ext:npm:yaml" in message("yaml") and "ext:python:yaml" in message("yaml")
