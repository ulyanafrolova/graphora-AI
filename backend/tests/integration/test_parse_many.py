"""Issue #8: parsing many files in one process must not corrupt memory (tree-sitter 0.26.0 segfaulted and reported
definition lines past the end of the file)."""

import subprocess
import sys

from conftest import REPO_ROOT

# Runs in a child process so a segfault fails this test instead of killing pytest.
_CHILD = """
import sys
from pathlib import Path

from graphora.adapters.js import extract as js
from graphora.adapters.python import extract as py
from graphora.detect.languages import ANALYZED_EXTENSIONS
from graphora.ingest.walk import EXCLUDED_DIRS

root = Path(sys.argv[1])
count = 0
for path in sorted(root.rglob("*")):
    rel = path.relative_to(root)
    if path.suffix not in ANALYZED_EXTENSIONS or any(p in EXCLUDED_DIRS for p in rel.parts) or not path.is_file():
        continue
    source = path.read_bytes()
    facts = py.extract(source) if ANALYZED_EXTENSIONS[path.suffix] == "python" else js.extract(str(rel), source)
    if facts is None:
        continue
    count += 1
    total = source.count(b"\\n") + 1
    lines = [d.line for d in facts.definitions] + [i.line for i in facts.imports]
    lines += [e.line for e in getattr(facts, "exports", ())]
    for line in lines:
        if not 1 <= line <= total:
            print(f"{rel}: line {line} outside 1..{total}")
print(f"parsed {count}")
"""


def test_parse_whole_repository_in_one_process():
    result = subprocess.run([sys.executable, "-c", _CHILD, str(REPO_ROOT)], capture_output=True, text=True)

    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    lines = result.stdout.splitlines()
    assert lines[-1].startswith("parsed ") and int(lines[-1].split()[1]) > 50, result.stdout
    assert lines[:-1] == []
