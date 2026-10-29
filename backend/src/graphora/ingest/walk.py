"""Read-only walk of the analyzed folder: skip rules, symlinks and limits (data-model.md § Skipped)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from graphora.graph.model import Skipped
from graphora.ingest.errors import BadInput

EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        "site-packages",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".next",
        ".nuxt",
        ".turbo",
        ".svelte-kit",
        "coverage",
        "out",
        "bower_components",
    }
)
MINIFIED_SUFFIXES = (".min.js", ".min.css")


class LimitExceeded(Exception):
    def __init__(self, limit: str, value: float, observed: float) -> None:
        super().__init__(f"{limit} limit exceeded: {observed} > {value}")
        self.limit = limit
        self.value = value
        self.observed = observed


class Deadline:
    """Wall-clock budget for one run. Used only to abort; never written to the output."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._start = time.monotonic()

    def check(self) -> None:
        elapsed = time.monotonic() - self._start
        if elapsed >= self.seconds:
            raise LimitExceeded("seconds", self.seconds, round(elapsed, 1))

    def remaining(self) -> float:
        return max(0.0, self.seconds - (time.monotonic() - self._start))


@dataclass(frozen=True)
class WalkResult:
    files: list[str]
    skipped: list[Skipped]
    total_bytes: int
    special: frozenset[str] = frozenset()  # FIFOs, sockets, devices: listed, never opened (a FIFO read blocks)


def is_excluded_path(rel: str) -> bool:
    """Name-based skip rules, also applied to paths read from git trees."""
    parts = rel.split("/")
    return any(p in EXCLUDED_DIRS for p in parts[:-1]) or parts[-1] == ".git" or parts[-1].endswith(MINIFIED_SUFFIXES)


def walk(root: Path, max_files: int, max_bytes: int, deadline: Deadline | None = None) -> WalkResult:
    files: list[str] = []
    special: list[str] = []
    skipped: list[Skipped] = []
    total = 0
    if deadline is not None:
        deadline.check()

    stack = [""]
    while stack:
        rel_dir = stack.pop()
        try:
            with os.scandir(root / rel_dir if rel_dir else root) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            # A folder that cannot be listed would silently drop files; schema v2 has no skip reason for it.
            raise BadInput(f"cannot read folder {rel_dir or '.'}: {exc.strerror or exc}") from exc
        subdirs = []
        for entry in entries:
            if deadline is not None:
                deadline.check()
            rel = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
            if entry.is_symlink():
                skipped.append(Skipped(rel, "symlink"))
            elif entry.name == ".git" or (entry.is_dir(follow_symlinks=False) and entry.name in EXCLUDED_DIRS):
                skipped.append(Skipped(rel, "excluded_dir"))
            elif entry.is_dir(follow_symlinks=False):
                if os.path.lexists(os.path.join(entry.path, ".git")):
                    skipped.append(Skipped(rel, "nested_repository"))
                else:
                    subdirs.append(rel)
            elif entry.is_file(follow_symlinks=False):
                if entry.name.endswith(MINIFIED_SUFFIXES):
                    skipped.append(Skipped(rel, "minified"))
                    continue
                files.append(rel)
                total += entry.stat(follow_symlinks=False).st_size
                if len(files) > max_files:
                    raise LimitExceeded("files", max_files, len(files))
                if total > max_bytes:
                    raise LimitExceeded("bytes", max_bytes, total)
            else:
                files.append(rel)
                special.append(rel)
                if len(files) > max_files:
                    raise LimitExceeded("files", max_files, len(files))
        stack.extend(reversed(subdirs))

    files.sort()
    skipped.sort(key=lambda s: s.path)
    return WalkResult(files=files, skipped=skipped, total_bytes=total, special=frozenset(special))


def read_file(root: Path, rel: str) -> bytes:
    """Read one walked file without following a symlink at the final component."""
    fd = os.open(root / rel, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as fh:
        return fh.read()
