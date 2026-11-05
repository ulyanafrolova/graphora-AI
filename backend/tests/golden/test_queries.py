"""Golden query answers: every fixture's queries.json, written by hand, must match the query layer
(specs/004-graph-queries research § R12, contracts/answers.md § Golden projection)."""

import json

import pytest

from conftest import FIXTURES, analyzed_graph
from graphora.graph import queries
from graphora.graph.load import loads
from graphora.graph.results import dumps

CASES = [
    pytest.param(p.parent.name, i, entry, id=f"{p.parent.name}-{i}-{entry['question']}")
    for p in sorted(FIXTURES.glob("*/queries.json"))
    for i, entry in enumerate(json.loads(p.read_text(encoding="utf-8")))
]
_QUESTIONS = {
    "dependencies": queries.dependencies,
    "dependents": queries.dependents,
    "impact": queries.impact,
    "cycles": queries.cycles,
    "neighbors": queries.neighbors,
    "key_files": queries.key_files,
}


def _ask(name, entry):
    ix = queries.index(loads(analyzed_graph(name)))
    ask = _QUESTIONS[entry["question"]]
    if entry["target"] is None:
        return ask(ix, **entry["options"])
    return ask(ix, entry["target"], **entry["options"])


def _path(node_id: str) -> str:
    return node_id.removeprefix("file:")


def _chain(chain: list[dict]) -> list[str]:
    return [f"{_path(link['source'])}:{link['edges'][0]['line']}" for link in chain]


def _items(items: list[dict]) -> list[dict]:
    out = []
    for i in items:
        item = {"node": i["node"], "chain": _chain(i["chain"])}
        for key in ("distance", "transitive_dependents", "direct_dependents"):
            if key in i:
                item[key] = i[key]
        if i["type_only"]:
            item["type_only"] = True
        if i["confidence"] != "resolved":
            item["confidence"] = i["confidence"]
        out.append(item)
    return out


def project_answer(answer: dict) -> dict:
    out: dict = {"total": answer["total"]}
    if answer["truncated"]:
        out["truncated"] = True
    for key in ("items", "outgoing", "incoming"):
        if key in answer:
            out[key] = _items(answer[key])
    if "groups" in answer:
        out["groups"] = [{"files": g["files"], "cycle": _chain(g["cycle"]), "type_only": g["type_only"]} for g in answer["groups"]]
    if "unresolved" in answer:
        out["unresolved"] = [f"{_path(e['source'])}:{e['line']} {e['reason']}" for e in answer["unresolved"]]
    if "cut" in answer:
        out["cut"] = answer["cut"]
    if "completeness" in answer:
        out["completeness"] = answer["completeness"]
    return out


@pytest.mark.parametrize("name, i, entry", CASES)
def test_matches_hand_written_answer(name, i, entry):
    answer = json.loads(dumps(_ask(name, entry)))
    assert project_answer(answer) == entry["expected"]


@pytest.mark.parametrize("name, i, entry", CASES)
def test_cited_edges_are_graph_edges_and_chains_connect(name, i, entry):
    graph_edges = {e["id"]: e for e in json.loads(analyzed_graph(name))["edges"]}
    answer = json.loads(dumps(_ask(name, entry)))
    for item in answer.get("items", []) + answer.get("outgoing", []) + answer.get("incoming", []):
        for link in item["chain"]:
            for e in link["edges"] + link["via"]:
                assert graph_edges[e["id"]] == e
        chain = item["chain"]
        for a, b in zip(chain, chain[1:], strict=False):
            assert a["target"] == b["source"]
        if chain:
            end = item["node"] if item in answer.get("outgoing", []) or answer["question"] == "dependencies" else answer["target"]
            assert chain[-1]["target"] == end
    for group in answer.get("groups", []):
        cycle = group["cycle"]
        for link in cycle:
            for e in link["edges"]:
                assert graph_edges[e["id"]] == e
        for a, b in zip(cycle, cycle[1:] + cycle[:1], strict=True):
            assert a["target"] == b["source"]
        assert cycle[0]["source"] == group["files"][0]
    for e in answer.get("unresolved", []):
        assert graph_edges[e["id"]] == e


@pytest.mark.parametrize("name, i, entry", CASES)
def test_same_question_twice_same_bytes(name, i, entry):
    assert dumps(_ask(name, entry)) == dumps(_ask(name, entry))
