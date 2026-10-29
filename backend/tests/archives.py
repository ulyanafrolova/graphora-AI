"""In-memory tar.gz and ZIP archives for tests (specs/002-repo-ingest/research.md § R10).

An entry is `(name, kind, data_or_target, mode)`; `name` may be raw `bytes`; the last two fields are optional.
"""

from __future__ import annotations

import gzip
import io
import os
import stat
import tarfile
import zipfile
from collections.abc import Collection, Iterable, Sequence
from pathlib import Path

_TAR_TYPES = {
    "file": tarfile.REGTYPE,
    "dir": tarfile.DIRTYPE,
    "symlink": tarfile.SYMTYPE,
    "hardlink": tarfile.LNKTYPE,
    "chr": tarfile.CHRTYPE,
    "fifo": tarfile.FIFOTYPE,
}
_ZIP_TYPES = {
    "file": stat.S_IFREG,
    "dir": stat.S_IFDIR,
    "symlink": stat.S_IFLNK,
    "chr": stat.S_IFCHR,
    "fifo": stat.S_IFIFO,
}
_DEFAULT_MODES = {"dir": 0o755, "symlink": 0o777}
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_CHUNK = 1 << 20


def _unpack(entry: Sequence[object]) -> tuple:
    name, kind, *rest = entry
    data = rest[0] if rest else None
    mode = rest[1] if len(rest) > 1 and rest[1] is not None else _DEFAULT_MODES.get(kind, 0o644)
    return name, kind, data, mode


def _as_bytes(data) -> bytes:
    if data is None:
        return b""
    return data.encode("utf-8") if isinstance(data, str) else data


class _Zeros(io.RawIOBase):
    def __init__(self, size: int) -> None:
        self._left = size

    def readable(self) -> bool:
        return True

    def read(self, n: int = -1) -> bytes:
        n = self._left if n < 0 else min(n, self._left)
        self._left -= n
        return bytes(n)


def _tar_gz(members, pax_comment: str | None) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as gz:
        pax = {"comment": pax_comment} if pax_comment is not None else {}
        with tarfile.open(fileobj=gz, mode="w|", format=tarfile.PAX_FORMAT, pax_headers=pax) as tar:
            for info, fileobj in members:
                tar.addfile(info, fileobj)
    return buf.getvalue()


def _tar_member(name, kind: str, data, mode: int) -> tuple[tarfile.TarInfo, io.IOBase | None]:
    if kind not in _TAR_TYPES:
        raise ValueError(f"unknown entry kind: {kind}")
    if isinstance(name, bytes):
        name = name.decode("utf-8", "surrogateescape")  # tarfile writes the same bytes back
    info = tarfile.TarInfo(name)
    info.type = _TAR_TYPES[kind]
    info.mode = mode
    info.mtime = 0
    if kind == "file":
        content = _as_bytes(data)
        info.size = len(content)
        return info, io.BytesIO(content)
    if kind in ("symlink", "hardlink"):
        info.linkname = str(data)
    return info, None


def make_tar_gz(entries: Iterable[Sequence[object]], pax_comment: str | None = None) -> bytes:
    """`pax_comment` writes a pax global header `comment=<value>`, as GitHub does with the commit SHA."""
    return _tar_gz((_tar_member(*_unpack(e)) for e in entries), pax_comment)


class _ZipInfo(zipfile.ZipInfo):
    # zipfile resets flag_bits on write, but takes the stored name and flags from this method.
    raw_name: bytes | None = None
    extra_flags = 0

    def _encodeFilenameFlags(self) -> tuple[bytes, int]:
        if self.raw_name is not None:
            name, flags = self.raw_name, self.flag_bits & ~0x800
        else:
            name, flags = super()._encodeFilenameFlags()
        return name, flags | self.extra_flags


def _zip_info(name, kind: str, mode: int, utf8_flag: bool) -> _ZipInfo:
    if kind not in _ZIP_TYPES:
        raise ValueError(f"ZIP cannot hold entry kind: {kind}")
    if kind == "dir" and isinstance(name, str) and not name.endswith("/"):
        name += "/"
    elif kind == "dir" and isinstance(name, bytes) and not name.endswith(b"/"):
        name += b"/"
    if isinstance(name, bytes) or (not utf8_flag and not name.isascii()):
        raw = name if isinstance(name, bytes) else name.encode("utf-8")
        info = _ZipInfo(raw.decode("cp437"), _ZIP_DATE)
        info.raw_name = raw
    else:
        info = _ZipInfo(name, _ZIP_DATE)
    info.create_system = 3  # Unix: external_attr carries the file type
    info.external_attr = (_ZIP_TYPES[kind] | mode) << 16
    if kind == "dir":
        info.external_attr |= 0x10
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def make_zip(entries: Iterable[Sequence[object]], utf8_flag: bool = True, encrypted: Collection[str] = ()) -> bytes:
    """`utf8_flag=False` stores non-ASCII names without the UTF-8 flag; names in `encrypted` get the flag bit only."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for entry in entries:
            name, kind, data, mode = _unpack(entry)
            info = _zip_info(name, kind, mode, utf8_flag)
            if name in encrypted:
                info.extra_flags = 0x1
            zf.writestr(info, str(data).encode("utf-8") if kind == "symlink" else _as_bytes(data))
    return buf.getvalue()


def _tree(path: Path, exclude: Collection[str]) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []

    def visit(folder: Path, rel: str) -> None:
        for child in sorted(os.listdir(folder)):
            if not rel and child in exclude:
                continue
            found.append((rel + child, folder / child))
            if stat.S_ISDIR(os.lstat(folder / child).st_mode):
                visit(folder / child, rel + child + "/")

    visit(path, "")
    return found


def _dir_entries(path: Path, prefix: str | None, exclude: Collection[str]) -> list[tuple]:
    head = f"{prefix}/" if prefix else ""
    entries: list[tuple] = [(prefix, "dir", None, 0o755)] if prefix else []
    for rel, full in _tree(path, exclude):
        mode = os.lstat(full).st_mode
        if stat.S_ISLNK(mode):
            entries.append((head + rel, "symlink", os.readlink(full), 0o777))
        elif stat.S_ISDIR(mode):
            entries.append((head + rel, "dir", None, 0o755))
        else:
            entries.append((head + rel, "file", full.read_bytes(), 0o644))
    return entries


def tar_of_dir(path: Path, prefix: str, pax_comment: str | None = None, exclude: Collection[str] = ()) -> bytes:
    """A tar.gz shaped like a GitHub tarball: everything under `prefix/`, symlinks kept."""
    return make_tar_gz(_dir_entries(path, prefix, exclude), pax_comment)


def zip_of_dir(path: Path, prefix: str | None = None, exclude: Collection[str] = ()) -> bytes:
    return make_zip(_dir_entries(path, prefix, exclude))


def bomb_zip(size: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        info = zipfile.ZipInfo("bomb.bin", _ZIP_DATE)
        info.compress_type = zipfile.ZIP_DEFLATED
        with zf.open(info, "w", force_zip64=size >= zipfile.ZIP64_LIMIT) as out:
            zeros = _Zeros(size)
            while chunk := zeros.read(_CHUNK):
                out.write(chunk)
    return buf.getvalue()


def bomb_tar_gz(size: int) -> bytes:
    info = tarfile.TarInfo("bomb.bin")
    info.size = size
    info.mode = 0o644
    return _tar_gz([(info, _Zeros(size))], None)
