"""Safe extraction (specs/002-repo-ingest research.md § R5, R6, R9; data-model.md § Archive entry classification)."""

import hashlib
import io
import os
import stat
import subprocess
import unicodedata
import zipfile

import pytest

from archives import bomb_tar_gz, bomb_zip, make_tar_gz, make_zip
from graphora.graph.model import Skipped
from graphora.ingest import archive
from graphora.ingest.archive import extract_tar_gz, extract_zip
from graphora.ingest.errors import InvalidArchive, RemoteError, UnsafeArchive
from graphora.ingest.fetch import IngestLimits
from graphora.ingest.walk import Deadline, LimitExceeded

FORMATS = ["tar", "zip"]


def _noise(n):
    return b"".join(hashlib.sha256(str(i).encode()).digest() for i in range(n // 32 + 1))[:n]


def _run(fmt, data, tmp_path, limits=None, deadline=None, sha=None):
    dest = tmp_path / "x"
    dest.mkdir()
    limits = limits or IngestLimits()
    deadline = deadline or Deadline(300)
    try:
        if fmt == "tar":
            return extract_tar_gz(io.BytesIO(data), dest, limits, deadline, sha)
        path = tmp_path / "in.zip"
        path.write_bytes(data)
        return extract_zip(path, dest, limits, deadline)
    finally:
        assert set(os.listdir(tmp_path)) <= {"x", "in.zip"}


def _extract(fmt, entries, tmp_path, **kwargs):
    data = make_tar_gz(entries) if fmt == "tar" else make_zip(entries)
    return _run(fmt, data, tmp_path, **kwargs)


def _listing(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


# --- paths (T012) -------------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize(
    "name, shown",
    [
        ("/etc/x", "/etc/x"),
        ("C:/x", "C:/x"),
        ("c:x", "c:x"),
        ("a\\b", "a\\b"),
        ("a/../../x", "a/../../x"),
        ("..", ".."),
        ("a//b", "a//b"),
        ("./a", "./a"),
        (b"\xff.py", "\\xff.py"),
    ],
)
def test_unsafe_path_rejected(fmt, name, shown, tmp_path):
    with pytest.raises(UnsafeArchive) as exc:
        _extract(fmt, [(name, "file", "x")], tmp_path)
    assert shown in exc.value.message


def test_nul_in_zip_name_rejected(tmp_path):
    with pytest.raises(UnsafeArchive) as exc:
        _extract("zip", [(b"a\x00b.py", "file", "x")], tmp_path)
    assert "a\\x00b.py" in exc.value.message


def test_non_utf8_zip_name_without_flag_rejected(tmp_path):
    with pytest.raises(UnsafeArchive):
        _run("zip", make_zip([(b"\xff.py", "file", "x")], utf8_flag=False), tmp_path)


def test_utf8_zip_name_without_flag_accepted(tmp_path):
    root, _ = _run("zip", make_zip([("café.py", "file", "x")], utf8_flag=False), tmp_path)
    assert (root / "café.py").read_bytes() == b"x"


# --- links and special entries (T013) -----------------------------------------------------------


@pytest.mark.parametrize("fmt", FORMATS)
def test_symlink_not_created_and_reported(fmt, tmp_path):
    root, skipped = _extract(fmt, [("a.py", "file", "x"), ("link.py", "symlink", "../../etc/passwd")], tmp_path)
    assert not os.path.lexists(root / "link.py")
    assert skipped == (Skipped("link.py", "symlink"),)


def test_hardlink_rejected(tmp_path):
    with pytest.raises(UnsafeArchive) as exc:
        _extract("tar", [("a.py", "file", "x"), ("h.py", "hardlink", "a.py")], tmp_path)
    assert "h.py" in exc.value.message


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("kind", ["chr", "fifo"])
def test_special_entry_rejected(fmt, kind, tmp_path):
    with pytest.raises(UnsafeArchive) as exc:
        _extract(fmt, [("dev", kind)], tmp_path)
    assert "dev" in exc.value.message


@pytest.mark.parametrize("fmt", FORMATS)
def test_entry_under_symlink_rejected(fmt, tmp_path):
    with pytest.raises(UnsafeArchive) as exc:
        _extract(fmt, [("link.py", "symlink", "/tmp"), ("link.py/inner.py", "file", "x")], tmp_path)
    assert "link.py/inner.py" in exc.value.message


@pytest.mark.parametrize("fmt", FORMATS)
def test_symlink_over_folder_rejected(fmt, tmp_path):
    with pytest.raises(UnsafeArchive):
        _extract(fmt, [("link.py/inner.py", "file", "x"), ("link.py", "symlink", "/tmp")], tmp_path)


# --- collisions (T014) --------------------------------------------------------------------------


NFC = unicodedata.normalize("NFC", "café.py")
NFD = unicodedata.normalize("NFD", "café.py")


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize(
    "first, second", [("a.py", "a.py"), ("A.py", "a.py"), (NFC, NFD), ("a", "a/b.py"), ("a/b.py", "a")]
)
def test_collision_rejected(fmt, first, second, tmp_path):
    with pytest.raises(UnsafeArchive) as exc:
        _extract(fmt, [(first, "file", "1"), (second, "file", "2")], tmp_path)
    assert first in exc.value.message and second in exc.value.message


# --- limits (T015) ------------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", FORMATS)
def test_bomb_stops_at_extract_limit(fmt, tmp_path, monkeypatch):
    written = []

    def counting_write(fd, data):
        written.append(len(data))
        return os.write(fd, data)

    monkeypatch.setattr(archive, "_write", counting_write)
    limit = 1_000_000
    data = bomb_tar_gz(100 * limit) if fmt == "tar" else bomb_zip(100 * limit)
    with pytest.raises(LimitExceeded) as exc:
        _run(fmt, data, tmp_path, limits=IngestLimits(max_extract_bytes=limit))
    assert exc.value.limit == "extract_bytes"
    assert sum(written) <= limit


@pytest.mark.parametrize("fmt", FORMATS)
def test_entry_limit(fmt, tmp_path):
    entries = [(f"f{i}.py", "file", "x") for i in range(11)]
    with pytest.raises(LimitExceeded) as exc:
        _extract(fmt, entries, tmp_path, limits=IngestLimits(max_entries=10))
    assert exc.value.limit == "entries"
    if fmt == "zip":
        assert os.listdir(tmp_path / "x") == []


def test_tar_stream_over_archive_limit(tmp_path):
    data = make_tar_gz([("big.bin", "file", _noise(300_000))])
    with pytest.raises(LimitExceeded) as exc:
        _run("tar", data, tmp_path, limits=IngestLimits(max_archive_bytes=100_000))
    assert exc.value.limit == "archive_bytes"


def test_zip_file_over_archive_limit(tmp_path):
    data = make_zip([("big.bin", "file", _noise(300_000))])
    with pytest.raises(LimitExceeded) as exc:
        _run("zip", data, tmp_path, limits=IngestLimits(max_archive_bytes=100_000))
    assert exc.value.limit == "archive_bytes"


@pytest.mark.parametrize("fmt", FORMATS)
def test_expired_deadline(fmt, tmp_path):
    with pytest.raises(LimitExceeded) as exc:
        _extract(fmt, [("a.py", "file", "x")], tmp_path, deadline=Deadline(0))
    assert exc.value.limit == "seconds"


# --- content safety (T016) ----------------------------------------------------------------------


@pytest.mark.parametrize("fmt", FORMATS)
def test_modes_are_plain(fmt, tmp_path):
    root, _ = _extract(
        fmt, [("d", "dir", None, 0o777), ("d/run.sh", "file", "x", 0o755), ("suid", "file", "x", 0o4755)], tmp_path
    )
    assert stat.S_IMODE(os.stat(root / "d/run.sh").st_mode) == 0o644
    assert stat.S_IMODE(os.stat(root / "suid").st_mode) == 0o644
    assert stat.S_IMODE(os.stat(root / "d").st_mode) == 0o755


@pytest.mark.parametrize("fmt", FORMATS)
def test_nothing_is_run(fmt, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("subprocess started")

    monkeypatch.setattr(subprocess, "Popen", fail)
    monkeypatch.setattr(os, "system", fail)
    marker = tmp_path / "ran"
    setup = f"open({str(marker)!r}, 'w').close()\n"
    package = '{"scripts": {"postinstall": "touch ' + str(marker) + '"}}'
    _extract(fmt, [("setup.py", "file", setup), ("package.json", "file", package)], tmp_path)
    assert not marker.exists()


# --- markers, root, invalid archives (T017) -----------------------------------------------------


@pytest.mark.parametrize("fmt", FORMATS)
def test_skipped_content_becomes_empty_markers(fmt, tmp_path):
    root, skipped = _extract(
        fmt,
        [
            ("a.py", "file", "x"),
            ("node_modules/pkg/index.js", "file", "x"),
            ("node_modules/.bin/tool", "symlink", "../pkg/index.js"),
            (".venv/lib/site.py", "file", "x"),
            (".git/HEAD", "file", "ref: refs/heads/main\n"),
            ("sub/.git/HEAD", "file", "ref"),
            ("sub/b.py", "file", "x"),
            ("sub/link.py", "symlink", "b.py"),
            ("x.min.js", "file", "minified"),
        ],
        tmp_path,
    )
    for folder in ("node_modules", ".venv", ".git", "sub/.git"):
        assert (root / folder).is_dir() and os.listdir(root / folder) == []
    assert (root / "x.min.js").stat().st_size == 0
    assert skipped == ()


@pytest.mark.parametrize("fmt", FORMATS)
def test_single_top_folder_is_root(fmt, tmp_path):
    root, skipped = _extract(
        fmt, [("proj", "dir"), ("proj/a.py", "file", "x"), ("proj/l.py", "symlink", "a.py")], tmp_path
    )
    assert root == tmp_path / "x" / "proj"
    assert skipped == (Skipped("l.py", "symlink"),)


@pytest.mark.parametrize("fmt", FORMATS)
def test_extra_top_entry_keeps_extraction_folder(fmt, tmp_path):
    root, _ = _extract(fmt, [("proj/a.py", "file", "x"), ("README", "file", "x")], tmp_path)
    assert root == tmp_path / "x"


@pytest.mark.parametrize("fmt", FORMATS)
def test_wrapper_named_like_skipped_folder(fmt, tmp_path):
    root, _ = _extract(fmt, [("build", "dir"), ("build/a.py", "file", "x")], tmp_path)
    assert root == tmp_path / "x" / "build"
    assert (root / "a.py").read_bytes() == b"x"


def test_pax_sha_mismatch(tmp_path):
    data = make_tar_gz([("p", "dir"), ("p/a.py", "file", "x")], pax_comment="b" * 40)
    with pytest.raises(RemoteError):
        _run("tar", data, tmp_path, sha="a" * 40)


def test_pax_sha_match(tmp_path):
    data = make_tar_gz([("p", "dir"), ("p/a.py", "file", "x")], pax_comment="a" * 40)
    root, _ = _run("tar", data, tmp_path, sha="a" * 40)
    assert _listing(root) == ["a.py"]


def _patch_zip_method(data, method):
    data = bytearray(data)
    for sig, offset in ((b"PK\x03\x04", 8), (b"PK\x01\x02", 10)):
        i = data.find(sig)
        data[i + offset : i + offset + 2] = method.to_bytes(2, "little")
    return bytes(data)


def test_encrypted_zip_entry_invalid(tmp_path):
    with pytest.raises(InvalidArchive):
        _run("zip", make_zip([("a.py", "file", "x")], encrypted={"a.py"}), tmp_path)


def test_unsupported_zip_method_invalid(tmp_path):
    with pytest.raises(InvalidArchive):
        _run("zip", _patch_zip_method(make_zip([("a.py", "file", "x")]), 99), tmp_path)


def test_zip_crc_mismatch_invalid(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("a.py", "hello")
    with pytest.raises(InvalidArchive):
        _run("zip", buf.getvalue().replace(b"hello", b"jello"), tmp_path)


def test_truncated_gzip_invalid(tmp_path):
    data = make_tar_gz([("big.bin", "file", _noise(100_000))])
    with pytest.raises(InvalidArchive):
        _run("tar", data[: len(data) // 2], tmp_path)
