"""Golden tests: every fixture's output, projected, must equal its hand-checked expected.json."""

import json
import shutil
from pathlib import Path

import pytest

from graphora.adapters import csharp, js, msbuild, python
from graphora.adapters.msbuild import sln
from conftest import FIXTURES, REPO_ROOT, edge_key, project, run_analyze

FIXTURE_NAMES = sorted(p.name for p in FIXTURES.iterdir() if (p / "expected.json").is_file())


def _normalize(section: str, value):
    if section == "nodes":
        return sorted(value, key=lambda n: n["id"])
    if section == "edges":
        return sorted(value, key=edge_key)
    if section in ("coverage", "skipped"):
        return sorted(value, key=lambda x: x["path"])
    return value


def _analyze(path):
    code, out, err = run_analyze(path)
    assert code == 0, err
    return out


@pytest.mark.parametrize("name", FIXTURE_NAMES)
@pytest.mark.parametrize("section", ["nodes", "edges", "coverage", "skipped", "snapshot_kind"])
def test_matches_expected(name, section, validator):
    expected = json.loads((FIXTURES / name / "expected.json").read_text(encoding="utf-8"))
    if section not in expected:
        pytest.skip(f"{name} has no {section} section")
    doc = json.loads(_analyze(FIXTURES / name / "repo"))
    validator.validate(doc)
    actual = project(doc, {section})[section]
    assert _normalize(section, actual) == _normalize(section, expected[section])


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_provenance_consistent(name):
    doc = json.loads(_analyze(FIXTURES / name / "repo"))
    languages = {n["id"]: n["language"] for n in doc["nodes"] if n["kind"] == "file"}
    languages.update({n["id"]: "msbuild" for n in doc["nodes"] if n["kind"] == "project"})
    languages.update({n["id"]: "solution" for n in doc["nodes"] if n["kind"] == "solution"})
    extractors = {
        "python": python.EXTRACTOR,
        "typescript": js.EXTRACTOR,
        "javascript": js.EXTRACTOR,
        "csharp": csharp.EXTRACTOR,
        "msbuild": msbuild.EXTRACTOR,
        "solution": sln.EXTRACTOR,
    }
    for edge in doc["edges"]:
        assert edge["snapshot"] == doc["snapshot"]
        assert edge["extractor"] == extractors[languages[edge["source"]]]


V1 = Path(__file__).parent / "v1"


def _to_v1_id(node_id):
    return node_id.replace("ext:python:", "ext:", 1).replace("unresolved:python:", "unresolved:", 1)


@pytest.mark.parametrize("name", sorted(p.stem for p in V1.glob("*.json")))
def test_python_fixtures_match_v1(name):
    """SC-003: apart from the v2 fields, the Python nodes and edges equal the frozen v1 ground truth."""
    v1 = json.loads((V1 / f"{name}.json").read_text(encoding="utf-8"))
    actual = project(json.loads(_analyze(FIXTURES / name / "repo")), {"nodes", "edges"})
    nodes = []
    for n in actual["nodes"]:
        if n["kind"] == "file" and n["language"] != "python":
            continue
        item = {k: v for k, v in n.items() if k not in ("ecosystem", "language")}
        nodes.append(dict(item, id=_to_v1_id(n["id"])))
    edges = [
        {k: (_to_v1_id(v) if k == "target" else v) for k, v in e.items() if k not in ("type", "form")}
        for e in actual["edges"]
        if e["source"].endswith((".py", ".pyi"))
    ]
    v1_edge_key = lambda e: (e["source"], e["line"], e["target"], e["symbol"] or "")
    assert sorted(nodes, key=lambda n: n["id"]) == sorted(v1["nodes"], key=lambda n: n["id"])
    assert sorted(edges, key=v1_edge_key) == sorted(v1["edges"], key=v1_edge_key)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_determinism(name, tmp_path):
    source = FIXTURES / name / "repo"
    first = _analyze(source)
    for _ in range(9):
        assert _analyze(source) == first
    copy = tmp_path / "deep" / "other" / "path"
    shutil.copytree(source, copy, symlinks=True)
    assert _analyze(copy) == first
    text = first.decode("utf-8")
    assert str(REPO_ROOT) not in text and str(tmp_path) not in text


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_exports_invariant(name):
    """003 data-model § Export: every name a TS/JS file exports appears exactly once."""
    doc = json.loads(_analyze(FIXTURES / name / "repo"))
    for node in doc["nodes"]:
        if node["kind"] != "file" or node["language"] in ("python", "csharp"):
            continue
        # merged declarations (`interface X` + `class X`) share one exported binding: count it once per name
        names = list({(d["name"], n) for d in node["definitions"] for n in d["exported_as"]})
        names = [n for _, n in names]
        names += [x["name"] for x in node["exports"]]
        names += [
            e.get("alias") or e["symbol"]
            for e in doc["edges"]
            if e["source"] == node["id"] and e["type"] == "reexports" and (e["symbol"] != "*" or "alias" in e)
        ]
        assert len(names) == len(set(names)), (node["id"], sorted(names))


def _ecosystem(node_id):
    return node_id.split(":")[1]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_ecosystems_separate(name):
    """003 US3, 007 R7: a target's ecosystem always matches its source file's language."""
    doc = json.loads(_analyze(FIXTURES / name / "repo"))
    languages = {n["id"]: n["language"] for n in doc["nodes"] if n["kind"] == "file"}
    languages.update({n["id"]: "csharp" for n in doc["nodes"] if n["kind"] in ("project", "solution")})
    allowed = {"python": {"python"}, "typescript": {"npm"}, "javascript": {"npm"}, "csharp": {"dotnet", "nuget"}}
    for edge in doc["edges"]:
        if edge["target"].startswith(("ext:", "unresolved:")):
            assert _ecosystem(edge["target"]) in allowed[languages[edge["source"]]], edge


def test_mixed_fullstack_has_no_cross_language_edges():
    doc = json.loads(_analyze(FIXTURES / "mixed-fullstack" / "repo"))
    languages = {n["id"]: n["language"] for n in doc["nodes"] if n["kind"] == "file"}
    for edge in doc["edges"]:
        if edge["target"] in languages:
            assert (languages[edge["source"]] == "python") == (languages[edge["target"]] == "python"), edge
    assert {"python", "typescript"} <= set(doc["coverage"]["summary"]["by_language"])
    externals = {n["id"] for n in doc["nodes"] if n["kind"] == "external"}
    assert {"ext:python:yaml", "ext:npm:yaml"} <= externals


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_edge_ids_unique_and_endpoints_exist(name):
    doc = json.loads(_analyze(FIXTURES / name / "repo"))
    ids = [e["id"] for e in doc["edges"]]
    assert len(ids) == len(set(ids))
    nodes = {n["id"] for n in doc["nodes"]}
    assert all(e["source"] in nodes and e["target"] in nodes for e in doc["edges"])


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_csharp_files_point_at_existing_projects(name):
    """007 FR-009: a C# file's `project` is null or a project node of the same document."""
    doc = json.loads(_analyze(FIXTURES / name / "repo"))
    projects = {n["id"] for n in doc["nodes"] if n["kind"] == "project"}
    for n in doc["nodes"]:
        if n["kind"] == "file" and n["language"] == "csharp":
            assert n["project"] is None or n["project"] in projects, n["id"]
