"""Path normalization of the HTTP bridge (specs/015-http-bridge research R4, tasks T019)."""

import pytest

from graphora.resolve.http import display, normalize


@pytest.mark.parametrize("path", ["/users/{user_id}", "/users/{id:int}", "/users/<user_id>", "/users/<int:user_id>", "/users/{p}"])
def test_parameters(path):
    assert normalize(path) == ("users", "*")


@pytest.mark.parametrize("path", ["/api/items", "/api/items/", "/api/items?page=2", "/api/items#top", "//api//items", "api/items"])
def test_same_path(path):
    assert normalize(path) == ("api", "items")


def test_other_forms():
    assert normalize("/files/{path:path}") == ("files", "*")
    assert normalize("/v{n}/items") == ("*", "items")
    assert normalize("/") == ()
    assert display(normalize("/users/{id}/orders")) == "/users/{}/orders"
    assert display(()) == "/"
