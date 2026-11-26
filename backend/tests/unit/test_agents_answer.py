"""The answer built by code and the summary check (specs/012-agents FR-013, FR-014, research R7, tasks T015)."""

from graphora.agents.answer import UNRELATED, build_answer, check_summary, cite, parts, render_answer, sentence
from graphora.agents.claims import claim_key
from graphora.agents.state import Evidence, Hypothesis, Stated
from graphora.verify import Check, Claim, Step, Verdict

S = "snap"
DEP = Claim("dependency", "the routes need the service badly", S, steps=(Step("api/routes.py", 1, "auth/service.py", "AuthService"),))
LIKELY = Claim("dependency", "", S, steps=(Step("db.py", 1, "auth/service.py"),))
COUNT = Claim("query", "", S, question="dependents", target="auth/service.py", count=2)
BAD = Claim("dependency", "", S, steps=(Step("web/login.ts", 1, "auth/service.py"),))
OK, HEUR = Verdict("verified", (Check("edge", True, "x"),)), Verdict("heuristic", (Check("edge", True, "x"),))
NO = Verdict("rejected", (Check("edge", False, "x"),), "no_edge")


def stated(claim, rnd=0):
    return Stated(claim, claim_key(claim), rnd)


def state(**more):
    claims = [stated(DEP), stated(LIKELY), stated(COUNT), stated(BAD), stated(DEP)]
    verdicts = {claim_key(DEP): OK, claim_key(LIKELY): HEUR, claim_key(COUNT): OK, claim_key(BAD): NO}
    hyp = Hypothesis("h1", claim_key(BAD), BAD, "no_edge", None, 2)
    base = {"question": "what breaks?", "snapshot": S, "claims": claims, "verdicts": verdicts, "hypotheses": [hyp]}
    base["evidence"] = [Evidence("analyst", "dependents", {"target": "auth/service.py"}, ("c1",))]
    return base | more


def test_parts_and_templates():
    facts, likely, hyps = parts(state())
    assert [i.cite for i in facts] == ["api/routes.py:1@snap", "dependents(auth/service.py)@snap"]
    assert facts[0].text == "`api/routes.py` imports `auth/service.py` (name `AuthService`)"
    assert facts[1].text == "`auth/service.py` has 2 direct dependents"
    assert all("badly" not in i.text for i in facts)
    assert [i.cite for i in likely] == ["db.py:1@snap"]
    assert [(i.cite, i.reason) for i in hyps] == [("web/login.ts:1@snap", "no_edge")]


def test_every_kind_has_a_sentence_and_cite():
    claims = [
        Claim("chain", "", S, steps=(Step("a.py", 1, "b.py"), Step("b.py", 2, "a.py"))),
        Claim("chain", "", S, steps=(Step("a.py", 1, "b.py"), Step("b.py", 2, "c.py"))),
        Claim("definition", "", S, path="a.py", line=3, symbol="A"),
        Claim("mention", "", S, path="a.py", line=4, symbol="A"),
        Claim("query", "", S, question="impact", target="a.py", member="c.py", distance=2),
        Claim("query", "", S, question="key_files", target=None, member="a.py", rank=3),
        Claim("query", "", S, question="cycles", target=None, count=1),
    ]
    assert [sentence(c) for c in claims] == [
        "import cycle: `a.py` → `b.py` → `a.py`",
        "`a.py` depends on `c.py` through `a.py` → `b.py` → `c.py`",
        "`A` is defined in `a.py` at line 3",
        "line 4 of `a.py` mentions `A`",
        "`c.py` is among the files in its impact of `a.py` at distance 2",
        "`a.py` is among the 3 most depended-on files",
        "the snapshot has 1 import cycle",
    ]
    assert cite(claims[5]) == "key_files()@snap" and cite(claims[2]) == "a.py:3@snap"


def test_summary_check():
    facts, likely, _ = parts(state())
    assert check_summary("Changing auth/service.py breaks api/routes.py (api/routes.py:1). db.py likely too.", facts, likely)
    assert check_summary("service.py is used by routes.py.", facts, likely)
    assert not check_summary("It also breaks web/login.ts.", facts, likely)
    assert not check_summary("See api/routes.py:7.", facts, likely)
    assert not check_summary("See db.py:1.", facts, likely)
    assert not check_summary("And main.py too.", facts, likely)


def test_build_answer_uses_checked_summary():
    good = build_answer(state(), "auth/service.py is imported by api/routes.py.", "answered")
    assert good.summary_source == "model"
    bad = build_answer(state(), "web/login.ts breaks.", "answered")
    assert bad.summary_source == "code" and bad.summary == "Verified: 2 facts, 1 likely link, 1 hypothesis (not proven)."
    assert build_answer(state(), None, "answered").summary_source == "code"


def test_code_summaries():
    empty = {"question": "poem?", "snapshot": S}
    assert build_answer(empty, None, "no_claims").summary == UNRELATED
    missing = empty | {"evidence": [Evidence("explorer", "find_definitions", {"name": "Nope"}, error="no definition")]}
    assert build_answer(missing, None, "no_claims").summary == "`Nope` was not found in the snapshot; nothing could be verified."


def test_render():
    text = render_answer(build_answer(state(), None, "revisions_spent"))
    assert text.index("Facts") < text.index("Likely") < text.index("Hypotheses (not proven)") < text.index("Summary")
    assert "- `db.py` imports `auth/service.py` (db.py:1@snap), likely" in text
    assert "(web/login.ts:1@snap): no edge in the graph" in text
    assert text.endswith("snapshot snap · ended: revisions_spent\n")
    assert "(none)" in render_answer(build_answer({"question": "q", "snapshot": S}, None, "no_claims"))
