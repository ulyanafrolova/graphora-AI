"""Components and cycle cuts on a 5,000-file graph stay under 2 s each (specs/019-frontend T064)."""

import time

import pytest

from graphora.graph import queries
from graphora.graph.load import loads
from test_query_performance import _graph

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def ix():
    return queries.index(loads(_graph()))


@pytest.mark.parametrize("question", [queries.components, queries.cycles])
def test_under_two_seconds(ix, question):
    start = time.perf_counter()
    answer = question(ix)
    seconds = time.perf_counter() - start
    assert answer.total > 0
    assert seconds < 2, f"{question.__name__} took {seconds:.2f} s"
