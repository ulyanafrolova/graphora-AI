"""Edge positions on long lines and the time limit inside one file (audit: quadratic `_position`)."""

import time

import pytest

from graphora.adapters.js import extract as js
from graphora.adapters.python import extract as py


def test_columns_are_code_points_on_one_long_line():
    source = 'const s = "😀é"; const a = require("./a"); const b = require("./b");\n'
    lines_columns = [(r.line, r.column) for r in js.extract("a.js", source.encode("utf-8")).imports]
    expected = [(1, source.index('require("./a")') + 1), (1, source.index('require("./b")') + 1)]
    assert lines_columns == expected


def test_python_dynamic_calls_after_statements_on_the_same_line():
    """Calls are positioned after statements, so the helper must restart a line it has already passed."""
    source = 'x = __import__("os"); import sys; y = "é"; import json\n'
    records = py.extract(source.encode("utf-8")).imports
    assert [(r.line, r.column) for r in records] == [(1, 5), (1, 23), (1, 44)]


@pytest.mark.slow
def test_one_megabyte_line_is_linear():
    line = ";".join(f'var a{i}=require("./m{i % 50}")' for i in range(36000)).encode()
    start = time.monotonic()
    facts = js.extract("bundle.js", line)
    assert len(facts.imports) == 36000
    assert time.monotonic() - start < 3  # was about 7 s with a per-import scan from the line start


@pytest.mark.parametrize("run", [lambda c: js.extract("a.js", b"require('x');\n" * 5000, c), lambda c: py.extract(b"import x\n" * 5000, c)])
def test_time_limit_is_checked_inside_one_file(run):
    def check():
        raise TimeoutError

    with pytest.raises(TimeoutError):
        run(check)


def test_lone_cr_ends_a_line():
    py_records = py.extract(b"x = 1\rimport os\r\nimport sys\n")
    assert [(r.line, r.column) for r in py_records.imports] == [(2, 1), (3, 1)]
    assert not py_records.has_error
    js_records = js.extract("a.js", b'const a = 1;\rconst b = require("./b");\r')
    assert [(r.line, r.column) for r in js_records.imports] == [(2, 11)]
