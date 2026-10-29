"""Source detection and GitHub link rules (specs/002-repo-ingest data-model.md § Source, research.md § R2, R4, R14)."""

import pytest

from graphora.ingest.errors import BadInput
from archives import make_zip
from graphora.ingest.source import GitHubSource, LocalSource, ZipSource, parse_source


def test_folder(tmp_path):
    assert parse_source(str(tmp_path), None) == LocalSource(tmp_path)


@pytest.mark.parametrize(
    "link, expected",
    [
        ("https://github.com/o/r", GitHubSource("o", "r", None)),
        ("https://github.com/o/r.git", GitHubSource("o", "r", None)),
        ("https://github.com/o/r/", GitHubSource("o", "r", None)),
        ("https://GitHub.com/O/R", GitHubSource("o", "r", None)),
        ("https://github.com/o/r/tree/v1", GitHubSource("o", "r", "v1")),
    ],
)
def test_accepted_links(link, expected):
    assert parse_source(link, None) == expected


@pytest.mark.parametrize(
    "link",
    [
        "http://github.com/o/r",
        "https://gitlab.com/o/r",
        "https://github.com/o/r/blob/main/x.py",
        "https://github.com/o/r/extra",
        "https://github.com/o/r?x=1",
        "https://github.com/o/r#x",
        "https://github.com/o/r/tree/",
        "https://github.com/" + "o" * 40 + "/r",
        "https://github.com/o/..",
    ],
)
def test_rejected_links(link):
    with pytest.raises(BadInput) as exc:
        parse_source(link, None)
    assert "accepted: https://github.com/<owner>/<repo>" in exc.value.message


def test_tree_ref_with_slash_suggests_ref_option():
    with pytest.raises(BadInput) as exc:
        parse_source("https://github.com/o/r/tree/feature/x", None)
    assert "--ref" in exc.value.message


def test_ref_given_twice():
    with pytest.raises(BadInput) as exc:
        parse_source("https://github.com/o/r/tree/v1", "v1")
    assert "--ref given twice" in exc.value.message


@pytest.mark.parametrize("ref", ["a..b", "a b", "-x", "x.lock", "a~1", "a@{1}"])
def test_invalid_ref_names(ref):
    with pytest.raises(BadInput) as exc:
        parse_source("https://github.com/o/r", ref)
    assert "invalid ref name" in exc.value.message


def test_ref_option_with_slash():
    assert parse_source("https://github.com/o/r", "feature/x") == GitHubSource("o", "r", "feature/x")


# --- ZIP detection (T028) -----------------------------------------------------------------------


def test_zip_detected_by_content_not_extension(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(make_zip([("a.py", "file", "x")]))
    assert parse_source(str(path), None) == ZipSource(path)


def test_empty_zip_detected(tmp_path):
    path = tmp_path / "empty.zip"
    path.write_bytes(make_zip([]))
    assert path.read_bytes()[:4] == b"PK\x05\x06"
    assert parse_source(str(path), None) == ZipSource(path)


def test_text_file_is_not_a_zip(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("# hi\n")
    with pytest.raises(BadInput) as exc:
        parse_source(str(path), None)
    assert "not a directory or ZIP archive" in exc.value.message


def test_ref_with_zip(tmp_path):
    path = tmp_path / "p.zip"
    path.write_bytes(make_zip([("a.py", "file", "x")]))
    with pytest.raises(BadInput) as exc:
        parse_source(str(path), "main")
    assert "--ref is allowed only with a GitHub link" in exc.value.message
