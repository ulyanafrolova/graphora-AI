"""Definition and mention claims against file text (specs/011-claim-verifier spec US2, research § R6)."""

import pytest

from graphora.graph.model import CoverageFile, Definition, FileNode
from graphora.graph.queries import index
from graphora.store import FileText
from graphora.verify import Claim, Line, verify
from synthetic import SNAP, edge, make_doc

SERVICE = [""] * 50
SERVICE[11] = "class AuthService:"
SERVICE[13] = "    hasher = hash_password"
SERVICE[39] = "        hashed = hash_password_v2(pw)"
SERVICE[41] = "        log.write(Logger)"
APP = ["const $el = document.body;", "export const User = 1;"]


class Source:
    def __init__(self, files):
        self.files = files
        self.reads = []

    def get(self, path):
        self.reads.append(path)
        lines = self.files.get(path)
        if lines is None:
            return None
        if lines == "binary":
            return FileText(path, False, 0, 0, 0, ())
        return FileText(path, True, len(lines), 1, len(lines), tuple(lines))


def doc():
    service = FileNode(
        "auth/service.py",
        "python",
        (Definition("class", "AuthService", 12), Definition("method", "Logger.write", 42), Definition("class", "Mailer", 30)),
    )
    return make_doc(
        [edge("api/routes.py", "auth/service.py", 3)],
        files=["app.js", "logo.png"],
        nodes=[service],
        coverage=[CoverageFile("README.md", None, "not_code"), CoverageFile("logo.png", None, "not_code")],
    )


def source():
    return Source({"auth/service.py": SERVICE, "app.js": APP, "README.md": ["# AuthService"], "logo.png": "binary"})


def mention(path, line, symbol):
    return Claim("mention", "", SNAP, path=path, line=line, symbol=symbol)


def definition(path, line, symbol):
    return Claim("definition", "", SNAP, path=path, line=line, symbol=symbol)


def one(claim, text=None):
    (verdict,) = verify([claim], index(doc()), source() if text is None else text)
    return verdict


def test_mention_of_a_whole_name():
    v = one(mention("auth/service.py", 14, "hash_password"))
    assert (v.status, v.fact) == ("verified", True)
    assert v.proof == (Line("auth/service.py", 14, "    hasher = hash_password"),)
    assert [c.name for c in v.checks] == ["snapshot", "file", "text", "range", "symbol"]


def test_part_of_a_longer_name_is_not_the_name():
    v = one(mention("auth/service.py", 40, "hash_password"))
    assert (v.reason, v.hint) == ("symbol_not_on_line", "found on line 14")


@pytest.mark.parametrize(
    ("line", "symbol", "ok"),
    [(1, "$el", True), (1, "el", False), (2, "user", False), (2, "User", True), (2, "App.Models.User", True)],
)
def test_name_rules(line, symbol, ok):
    assert (one(mention("app.js", line, symbol)).status == "verified") is ok


def test_qualified_name_by_its_last_part():
    assert one(mention("auth/service.py", 42, "Logger.write")).status == "verified"


def test_line_out_of_range():
    v = one(mention("auth/service.py", 51, "AuthService"))
    assert (v.reason, v.hint) == ("line_out_of_range", "file has 50 lines")


def test_file_not_in_snapshot():
    assert one(mention("missing/x.py", 1, "A")).reason == "file_not_in_snapshot"


def test_not_code_file_has_text():
    assert one(mention("README.md", 1, "AuthService")).status == "verified"


def test_no_text():
    assert one(mention("logo.png", 1, "PNG")).reason == "text_unavailable"
    (v,) = verify([mention("auth/service.py", 14, "hash_password")], index(doc()))
    assert v.reason == "text_unavailable"
    assert one(mention("app.js", 1, "$el"), Source({})).reason == "text_unavailable"


def test_definition_in_the_graph_and_on_the_line():
    v = one(definition("auth/service.py", 12, "AuthService"))
    assert v.status == "verified"
    assert v.proof == (Line("auth/service.py", 12, "class AuthService:"),)
    assert one(definition("auth/service.py", 42, "Logger.write")).status == "verified"
    assert one(definition("auth/service.py", 42, "write")).status == "verified"


def test_definition_on_another_line():
    v = one(definition("auth/service.py", 13, "AuthService"))
    assert (v.reason, v.hint) == ("symbol_not_on_line", "defined on line 12")


def test_definition_not_in_the_graph():
    assert one(definition("auth/service.py", 14, "hash_password")).reason == "definition_not_in_graph"
    assert one(definition("app.js", 2, "User")).reason == "definition_not_in_graph"


def test_definition_line_without_the_name():
    """Mailer is defined on line 30 in the graph, but the stored line 30 is empty."""
    v = one(definition("auth/service.py", 30, "Mailer"))
    assert (v.reason, v.hint) == ("symbol_not_on_line", None)


def test_nearest_line_lower_wins():
    lines = ["x = Name", "", "", "y = Name"]
    v = one(mention("app.js", 2, "Name"), Source({"app.js": lines}))
    assert v.hint == "found on line 1"


def test_each_file_read_once_per_call():
    text = source()
    claims = [mention("auth/service.py", n, "hash_password") for n in (14, 40, 42)] + [mention("app.js", 1, "$el")]
    verify(claims, index(doc()), text)
    assert text.reads == ["auth/service.py", "app.js"]
