"""Body of `POST /api/v1/ask` (specs/013-ask-sse data-model.md § AskRequest, tasks T003)."""

import pytest

from graphora.api.ask import parse_ask
from graphora.api.errors import ApiError

OK = {"repository": "r", "snapshot": "s", "question": "  what breaks?  "}


def refused(body):
    with pytest.raises(ApiError) as exc:
        parse_ask(body)
    assert exc.value.kind == "bad_request" and exc.value.status == 400
    return exc.value.message


def test_accepts_and_trims():
    assert parse_ask(OK) == ("r", "s", "what breaks?")
    assert parse_ask(OK | {"question": "x" * 2000})[2] == "x" * 2000
    assert parse_ask(OK | {"question": " " + "x" * 2000 + " "})[2] == "x" * 2000


@pytest.mark.parametrize("body", [[], "q", 3, None])
def test_not_an_object(body):
    assert refused(body) == "the body must be a JSON object"


def test_unknown_key():
    assert refused(OK | {"model": "x", "a": 1}) == "unknown key: a"


@pytest.mark.parametrize("key", ["repository", "snapshot", "question"])
@pytest.mark.parametrize("value", [None, 3, "", "   "])
def test_missing(key, value):
    body = dict(OK)
    if value is None:
        del body[key]
    else:
        body[key] = value
    assert refused(body) == f"missing {key}"


def test_too_long():
    assert refused(OK | {"question": "x" * 2001}) == "question is longer than 2000 characters"
