"""SC-004: on a 5,000-file graph, loading and indexing take < 2 s and each query < 1 s (specs/004-graph-queries)."""

import random
import time

import pytest

from graphora.graph import queries, serialize
from graphora.graph.load import loads
from graphora.graph.model import CoverageFile, Edge, FileNode, GraphDocument

pytestmark = pytest.mark.slow

SNAP = "content:0123456789abcdef"
FILES = 5000


def _graph() -> bytes:
    """About 20,000 imports, mostly from later files to earlier ones (layers), plus a few loops."""
    rnd = random.Random(4)
    paths = [f"pkg{i // 100:02}/m{i:04}.py" for i in range(FILES)]
    pairs = set()
    for i in range(1, FILES):
        for _ in range(4):
            pairs.add((i, rnd.randrange(max(0, i - 400), i)))
    for i in range(0, FILES, 500):
        pairs.add((i, i + 7))  # i + 7 already depends on i, so this closes a loop
    edges = tuple(
        Edge(f"file:{paths[a]}", f"file:{paths[b]}", None, 1 + n, 1, SNAP, "resolved", None, "python-adapter@0.2.0", "sha256:0000000000000000")
        for n, (a, b) in enumerate(sorted(pairs))
    )
    doc = GraphDocument(
        snapshot=SNAP,
        extractors={"python-adapter": "0.2.0"},
        nodes=tuple(FileNode(p, "python") for p in paths),
        edges=edges,
        files=tuple(CoverageFile(p, "python", "analyzed") for p in paths),
        skipped=(),
    )
    return serialize.dumps(doc)


@pytest.fixture(scope="module")
def data() -> bytes:
    return _graph()


def _timed(call):
    start = time.perf_counter()
    result = call()
    return result, time.perf_counter() - start


def test_load_and_index_under_two_seconds(data):
    ix, seconds = _timed(lambda: queries.index(loads(data)))
    assert len(ix.doc.edges) > 19_000
    assert seconds < 2, f"load + index took {seconds:.2f} s"


def test_each_query_under_one_second(data):
    ix = queries.index(loads(data))
    top, seconds = _timed(lambda: queries.key_files(ix, limit=None))
    assert seconds < 1, f"key_files took {seconds:.2f} s"
    hub = top.items[0].node
    asks = {
        "dependencies": lambda: queries.dependencies(ix, hub),
        "dependents": lambda: queries.dependents(ix, hub),
        "impact": lambda: queries.impact(ix, hub),
        "neighbors": lambda: queries.neighbors(ix, hub),
        "cycles": lambda: queries.cycles(ix),
    }
    for name, ask in asks.items():
        answer, seconds = _timed(ask)
        assert seconds < 1, f"{name} took {seconds:.2f} s"
    assert queries.cycles(ix).total >= 1
    assert queries.impact(ix, hub).total > 100
