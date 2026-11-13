"""Upload names and client limits are checked before a job exists (specs/010 research § R9, tasks T020)."""

import pytest

from graphora.api.errors import ApiError
from graphora.api.jobs import check_zip_name, parse_limits, query_limits
from graphora.pipeline import PipelineLimits

SERVER = PipelineLimits()


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "../x.zip", "a/b.zip", "a\\b.zip", "x\x00.zip", "a" * 252 + ".zip", ".zip"],
)
def test_bad_names(name):
    with pytest.raises(ApiError) as exc:
        check_zip_name(name)
    assert exc.value.kind == "bad_request"


def test_name_length_counts_bytes():
    assert check_zip_name("é" * 123 + ".zip") == "é" * 123  # 250 bytes
    with pytest.raises(ApiError):
        check_zip_name("é" * 126 + ".zip")  # 256 bytes; 255 bytes also keeps the repository under 300


@pytest.mark.parametrize("name,repository", [("app.zip", "app"), ("my.repo.zip", "my.repo"), ("noext", "noext")])
def test_good_names(name, repository):
    assert check_zip_name(name) == repository


def test_lower_limits_are_accepted():
    limits = parse_limits({"max_files": 10, "max_seconds": 1.5}, SERVER)
    assert (limits.max_files, limits.max_seconds, limits.max_bytes) == (10, 1.5, SERVER.max_bytes)


@pytest.mark.parametrize(
    "given,key",
    [
        ({"max_files": 5001}, "max_files"),
        ({"max_files": 0}, "max_files"),
        ({"max_files": 1.5}, "max_files"),
        ({"max_files": True}, "max_files"),
        ({"max_files": "10"}, "max_files"),
        ({"max_seconds": 0.5}, "max_seconds"),
        ({"max_seconds": 301}, "max_seconds"),
        ({"max_things": 1}, "max_things"),
    ],
)
def test_bad_limits(given, key):
    with pytest.raises(ApiError) as exc:
        parse_limits(given, SERVER)
    assert exc.value.kind == "bad_request" and key in exc.value.message


def test_query_limits():
    limits = query_limits({"name": "a.zip", "max_archive_bytes": "100", "max_seconds": "2.5"}, SERVER)
    assert (limits.max_archive_bytes, limits.max_seconds) == (100, 2.5)
    for bad in ({"max_entries": "-1"}, {"max_entries": "1e3"}, {"max_seconds": "x"}):
        with pytest.raises(ApiError):
            query_limits(bad, SERVER)
