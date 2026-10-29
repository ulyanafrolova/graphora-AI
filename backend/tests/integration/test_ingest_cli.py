"""`graphora analyze` with the 002 sources (specs/002-repo-ingest/contracts/cli.md)."""

from conftest import FIXTURES, run_analyze

FLAT = FIXTURES / "py-flat" / "repo"


def test_ref_with_folder_is_usage_error():
    code, out, err = run_analyze(FLAT, "--ref", "main")
    assert code == 2 and out == b""
    assert "--ref is allowed only with a GitHub link" in err


def test_missing_path_message(tmp_path):
    code, out, err = run_analyze(tmp_path / "nope")
    assert code == 2 and out == b""
    assert "not a directory or ZIP archive" in err


def test_default_ingest_limits_change_nothing():
    plain = run_analyze(FLAT)
    explicit = run_analyze(
        FLAT,
        "--max-archive-bytes", "209715200",
        "--max-extract-bytes", "209715200",
        "--max-entries", "20000",
    )
    assert plain[0] == explicit[0] == 0
    assert plain[1] == explicit[1]
