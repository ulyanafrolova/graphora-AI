"""Safe extraction of tar.gz streams and ZIP files (specs/002-repo-ingest/research.md § R5, R6, R9).

Entries are checked and written by this module only: no `extract`/`extractall`, no links, no executable bits.
"""

from __future__ import annotations

import os
import re
import stat
import tarfile
import unicodedata
import zipfile
import zlib
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from graphora.graph.model import Skipped
from graphora.ingest.errors import InvalidArchive, RemoteError, UnsafeArchive
from graphora.ingest.walk import EXCLUDED_DIRS, MINIFIED_SUFFIXES, Deadline, LimitExceeded

if TYPE_CHECKING:
    from graphora.ingest.fetch import IngestLimits

CHUNK = 64 * 1024
_DRIVE = re.compile(r"^[A-Za-z]:")
_write = os.write  # replaced in tests to measure what reaches the disk


def _display(name: str) -> str:
    return name.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace").replace("\x00", "\\x00")


def _unsafe(name: str, reason: str) -> UnsafeArchive:
    return UnsafeArchive(f"unsafe archive entry {_display(name)}: {reason}")


def _check_name(name: str, is_dir: bool = False) -> list[str]:
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        raise _unsafe(name, "name is not valid UTF-8") from None
    if "\x00" in name or "\\" in name:
        raise _unsafe(name, "NUL or backslash in name")
    if name.startswith("/") or _DRIVE.match(name):
        raise _unsafe(name, "absolute path")
    path = name[:-1] if is_dir and name.endswith("/") else name
    parts = path.split("/")
    if ".." in parts:
        raise _unsafe(name, "path outside the folder")
    if any(p in ("", ".") for p in parts):
        raise _unsafe(name, "empty or '.' path segment")
    return parts


def _key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


class _Writer:
    """Writes checked entries under `dest` and records symlinks instead of creating them."""

    def __init__(self, dest: Path, limits: IngestLimits, deadline: Deadline, top: str | None = None) -> None:
        self.dest = dest
        self.top = top  # a single wrapper folder: name rules apply below it, not to it
        self._real_dest = os.path.realpath(dest)
        self._limits = limits
        self._deadline = deadline
        self._entries = 0
        self._bytes = 0
        self._seen: dict[str, tuple[str, str, str]] = {}  # key -> (kind, path as spelled, entry name)
        self._symlinks: list[str] = []

    def _marker(self, parts: list[str]) -> int | None:
        """Index of the first ancestor the walk skips by name; that folder is created empty."""
        for i, part in enumerate(parts[:-1]):
            if i == 0 and part == self.top and part != ".git":
                continue
            if part in EXCLUDED_DIRS:
                return i
        return None

    def _count(self) -> None:
        if self._entries + 1 > self._limits.max_entries:
            raise LimitExceeded("entries", self._limits.max_entries, self._entries + 1)
        self._entries += 1

    def _target(self, path: str, entry: str) -> str:
        target = os.path.join(self.dest, *path.split("/"))
        real = os.path.realpath(target)
        if real != self._real_dest and not real.startswith(self._real_dest + os.sep):
            raise _unsafe(entry, "path outside the folder")
        return target

    def _claim(self, path: str, kind: str, entry: str) -> bool:
        """False if `path` is already this folder; raises on any other clash."""
        seen = self._seen.get(_key(path))
        if seen is None:
            self._seen[_key(path)] = (kind, path, entry)
            return True
        seen_kind, spelled, other = seen
        if kind == "dir" and seen_kind == "dir" and spelled == path:
            return False
        if seen_kind == "symlink":
            raise _unsafe(entry, f"under symlink {_display(other)}")
        raise _unsafe(entry, f"duplicate of {_display(other)}")

    def _dirs(self, parts: list[str], entry: str) -> None:
        for i in range(1, len(parts) + 1):
            path = "/".join(parts[:i])
            if self._claim(path, "dir", entry):
                self._count()
                target = self._target(path, entry)
                os.mkdir(target, 0o755)
                os.chmod(target, 0o755)

    def add_dir(self, name: str) -> None:
        self._deadline.check()
        parts = _check_name(name, is_dir=True)
        marker = self._marker(parts + [""])
        self._dirs(parts if marker is None else parts[: marker + 1], name)

    def add_file(self, name: str, chunks: Iterable[bytes]) -> None:
        self._deadline.check()
        parts = _check_name(name)
        marker = self._marker(parts)
        if marker is not None:
            self._dirs(parts[: marker + 1], name)
            return
        self._dirs(parts[:-1], name)
        path = "/".join(parts)
        self._claim(path, "file", name)
        self._count()
        fd = os.open(self._target(path, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        try:
            os.fchmod(fd, 0o644)
            if parts[-1] == ".git" or parts[-1].endswith(MINIFIED_SUFFIXES):
                return
            for chunk in chunks:
                self._deadline.check()
                if self._bytes + len(chunk) > self._limits.max_extract_bytes:
                    raise LimitExceeded("extract_bytes", self._limits.max_extract_bytes, self._bytes + len(chunk))
                view = memoryview(chunk)
                while view:
                    view = view[_write(fd, view) :]
                self._bytes += len(chunk)
        finally:
            os.close(fd)

    def add_symlink(self, name: str) -> None:
        self._deadline.check()
        parts = _check_name(name)
        marker = self._marker(parts)
        if marker is not None:
            self._dirs(parts[: marker + 1], name)
            return
        self._dirs(parts[:-1], name)
        path = "/".join(parts)
        self._claim(path, "symlink", name)
        self._symlinks.append(path)

    def finish(self) -> tuple[Path, tuple[Skipped, ...]]:
        top = set(os.listdir(self.dest)) | {p for p in self._symlinks if "/" not in p}
        root, prefix = self.dest, ""
        if len(top) == 1:
            (only,) = top
            if os.path.isdir(self.dest / only) and not os.path.islink(self.dest / only):
                root, prefix = self.dest / only, only + "/"
        skipped = []
        for path in self._symlinks:
            if not path.startswith(prefix):
                continue
            rel = path[len(prefix) :]
            parts = rel.split("/")
            if any(p in EXCLUDED_DIRS for p in parts[:-1]):
                continue
            if any(os.path.lexists(root.joinpath(*parts[:i], ".git")) for i in range(1, len(parts))):
                continue  # inside a nested repository, which the walk does not enter
            skipped.append(Skipped(rel, "symlink"))
        return root, tuple(sorted(skipped, key=lambda s: s.path))


class _Counted:
    def __init__(self, stream: BinaryIO, limit: int) -> None:
        self._stream = stream
        self._limit = limit
        self._read = 0

    def read(self, n: int = -1) -> bytes:
        data = self._stream.read(n)
        self._read += len(data)
        if self._read > self._limit:
            raise LimitExceeded("archive_bytes", self._limit, self._read)
        return data


def _chunks(fileobj: BinaryIO) -> Iterator[bytes]:
    while chunk := fileobj.read(CHUNK):
        yield chunk


def _check_pax(tar: tarfile.TarFile, expected_sha: str | None) -> None:
    comment = tar.pax_headers.get("comment")
    if expected_sha is not None and comment is not None and comment != expected_sha:
        raise RemoteError(f"GitHub archive does not match commit {expected_sha}")


def extract_tar_gz(
    stream: BinaryIO, dest: Path, limits: IngestLimits, deadline: Deadline, expected_sha: str | None
) -> tuple[Path, tuple[Skipped, ...]]:
    writer = _Writer(dest, limits, deadline)
    try:
        with tarfile.open(fileobj=_Counted(stream, limits.max_archive_bytes), mode="r|gz") as tar:
            first = True
            for member in tar:
                if first:
                    _check_pax(tar, expected_sha)
                    if member.isdir() and "/" not in member.name:
                        writer.top = member.name  # GitHub writes `<owner>-<repo>-<sha7>/` first
                    first = False
                name = member.name
                if member.issparse() or member.islnk() or member.ischr() or member.isblk() or member.isfifo():
                    raise _unsafe(name, "not a regular file, folder or symlink")
                if member.isreg():
                    fileobj = tar.extractfile(member)
                    writer.add_file(name, _chunks(fileobj) if fileobj else ())
                elif member.isdir():
                    writer.add_dir(name)
                elif member.issym():
                    writer.add_symlink(name)
                else:
                    raise _unsafe(name, "unknown entry type")
            _check_pax(tar, expected_sha)
    except (tarfile.TarError, EOFError, zlib.error) as exc:
        raise InvalidArchive(f"invalid tar.gz archive: {exc}") from None
    return writer.finish()


def _zip_name(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x800:
        return info.orig_filename
    try:
        return info.orig_filename.encode("cp437").decode("utf-8")
    except UnicodeDecodeError:
        return info.orig_filename.encode("cp437").decode("utf-8", "surrogateescape")


def _zip_top(names: list[str]) -> str | None:
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) != 1:
        return None
    (top,) = tops
    return top if all(n.startswith(top + "/") for n in names) else None


def extract_zip(path: Path, dest: Path, limits: IngestLimits, deadline: Deadline) -> tuple[Path, tuple[Skipped, ...]]:
    size = path.stat().st_size
    if size > limits.max_archive_bytes:
        raise LimitExceeded("archive_bytes", limits.max_archive_bytes, size)
    invalid = f"invalid ZIP archive {path.name}"
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if len(infos) > limits.max_entries:
                raise LimitExceeded("entries", limits.max_entries, len(infos))
            names = [_zip_name(info) for info in infos]
            writer = _Writer(dest, limits, deadline, _zip_top(names))
            for info, name in zip(infos, names):
                if info.flag_bits & 0x1:
                    raise InvalidArchive(f"{invalid}: encrypted entry {_display(name)}")
                kind = stat.S_IFMT(info.external_attr >> 16)
                if kind == stat.S_IFLNK:
                    writer.add_symlink(name)
                elif kind == stat.S_IFDIR or name.endswith("/"):
                    writer.add_dir(name)
                elif kind in (0, stat.S_IFREG):
                    writer.add_file(name, _zip_chunks(zf, info))
                else:
                    raise _unsafe(name, "not a regular file, folder or symlink")
    except UnicodeDecodeError:
        raise UnsafeArchive(f"unsafe archive entry in {path.name}: name is not valid UTF-8") from None
    except (zipfile.BadZipFile, NotImplementedError, zlib.error, EOFError) as exc:
        raise InvalidArchive(f"{invalid}: {exc}") from None
    return writer.finish()


def _zip_chunks(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> Iterator[bytes]:
    with zf.open(info) as fileobj:
        yield from _chunks(fileobj)
