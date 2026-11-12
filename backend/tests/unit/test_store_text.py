"""005 research § R5: decoding and line numbering of stored files match the adapters."""

from __future__ import annotations

import json

import pytest

from conftest import FIXTURES
from graphora.adapters.text import decode, split_lines, text_lines
from graphora.graph.build import analyze
from graphora.graph.serialize import to_dict
from graphora.ingest.walk import Deadline


def test_split_lines():
    assert split_lines("a\nb\r\nc\rd") == ("a", "b", "c", "d")
    assert split_lines("a\n") == ("a",)
    assert split_lines("") == ()
    assert split_lines("\n") == ("",)
    assert split_lines("a\n\nb") == ("a", "", "b")
    # characters str.splitlines() would split on are not line ends for the adapters
    assert split_lines("a\x0cb c\x1dd") == ("a\x0cb c\x1dd",)


def test_decode_rules():
    latin = b"# -*- coding: latin-1 -*-\nname = '\xe9'\n"
    assert decode("x.py", latin) == latin.decode("latin-1")
    assert decode("x.ts", latin) is None
    assert decode("x.py", b"a = 1\x00\n") is None
    assert decode("x.txt", b"\xff\xfe") is None
    assert decode("x.ts", "const s = 'é'\n".encode()) == "const s = 'é'\n"


def test_bom_removed_from_first_line_only():
    data = "﻿import a\n﻿b\n".encode()
    assert text_lines("x.ts", data) == ("import a", "﻿b")
    assert text_lines("x.py", data) == ("import a", "﻿b")


def test_no_text():
    assert text_lines("logo.png", b"\x89PNG\r\n\x1a\n\x00\x00") is None
    assert text_lines("empty.ts", b"") == ()


_STATEMENT_WORDS = ("import", "from", "export", "require", "using", "Reference")  # 007: C# and .csproj


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.iterdir() if (p / "expected.json").is_file()))
def test_expected_edge_lines_start_an_import(name):
    """Line N of an expected edge exists and holds the start of its statement. The symbol itself may be on a
    later line of a multi-line import, so it is not checked."""
    root = FIXTURES / name / "repo"
    expected = json.loads((FIXTURES / name / "expected.json").read_text(encoding="utf-8"))
    for edge in expected.get("edges", []):
        path = edge["source"].split(":", 1)[1]  # file:… or project:…
        lines = text_lines(path, (root / path).read_bytes())
        if lines is None:
            continue  # a file without text (e.g. invalid UTF-8) has no served lines
        assert 1 <= edge["line"] <= len(lines), (path, edge["line"])
        line = lines[edge["line"] - 1]
        if edge["type"] == "type_reference":  # 008: a use of the type, not an import statement
            assert edge["symbol"].rsplit(".", 1)[-1].removesuffix("Attribute") in line, (path, edge["line"], line)
            continue
        assert any(word in line for word in _STATEMENT_WORDS), (path, edge["line"], line)


def test_lone_cr_line_numbers(tmp_path):
    (tmp_path / "a.py").write_bytes(b"import os\rimport b\r")
    (tmp_path / "b.py").write_bytes(b"")
    doc = to_dict(analyze(tmp_path, 5000, 50 * 1024 * 1024, Deadline(300)).doc)
    [edge] = [e for e in doc["edges"] if e["target"] == "file:b.py"]
    assert edge["line"] == 2
    assert text_lines("a.py", (tmp_path / "a.py").read_bytes())[1] == "import b"
