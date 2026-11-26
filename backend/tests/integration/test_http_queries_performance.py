"""SC-003: on a stored 5,000-file graph each question route answers in < 3 s (specs/018-http-queries)."""

import time

import pytest
from fastapi.testclient import TestClient

from graphora.api import create_app
from graphora.graph.build import Analysis
from graphora.graph.load import loads
from test_query_performance import SNAP, _graph

pytestmark = [pytest.mark.slow, pytest.mark.db]

CENTRAL = "pkg00/m0000.py"
ROUTES = {
    "dependencies": {"target": CENTRAL},
    "dependents": {"target": CENTRAL},
    "impact": {"target": CENTRAL, "limit": "500"},
    "neighbors": {"target": CENTRAL},
    "cycles": {"limit": "500"},
    "key_files": {},
    "definitions": {"name": "anything"},
    "overview": {},
    "projects": {},
}


def test_each_question_under_three_seconds(store):
    doc = loads(_graph())
    store.put("perf", Analysis(doc=doc, warnings=(), contents={f.path: b"x = 1\n" for f in doc.files}))
    client = TestClient(create_app(store))
    for question, params in ROUTES.items():
        start = time.perf_counter()
        response = client.get(f"/api/v1/{question}", params={"repository": "perf", "snapshot": SNAP} | params)
        seconds = time.perf_counter() - start
        assert response.status_code == 200, response.text
        assert seconds < 3, f"{question} took {seconds:.2f} s"
