import hashlib
import re

from graphora.graph.serialize import snippet_hash
from graphora.ingest.snapshot import content_hash


def test_content_hash_definition():
    contents = {"b.py": b"2", "a.py": b"1"}
    h = hashlib.sha256()
    for path in ["a.py", "b.py"]:
        h.update(path.encode() + b"\0" + hashlib.sha256(contents[path]).hexdigest().encode() + b"\n")
    assert content_hash(contents) == h.hexdigest()[:16]


def test_content_hash_independent_of_location(tmp_path):
    for base in ["one", "deep/two"]:
        (tmp_path / base).mkdir(parents=True)
        (tmp_path / base / "a.py").write_bytes(b"import os\n")
    read = lambda base: {"a.py": (tmp_path / base / "a.py").read_bytes()}
    assert content_hash(read("one")) == content_hash(read("deep/two"))


def test_content_hash_changes_with_one_byte():
    assert content_hash({"a.py": b"import os\n"}) != content_hash({"a.py": b"import oz\n"})


def test_snippet_hash_whitespace_normalized():
    a = snippet_hash("from  a  import (b,\n c)")
    assert a == snippet_hash("from a import (b, c)")
    assert a != snippet_hash("from a import b")
    assert re.fullmatch(r"sha256:[0-9a-f]{16}", a)
