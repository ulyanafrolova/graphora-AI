"""Read tsconfig.json / jsconfig.json as data (specs/003-ts-js-analysis/research.md § R4).

Only `extends`, `compilerOptions.baseUrl` and `compilerOptions.paths` are used. Every path stays inside the
analyzed folder: configs and `extends` targets must be walked, non-skipped files.
"""

from __future__ import annotations

import json
import posixpath
from collections.abc import Callable
from dataclasses import dataclass

CONFIG_NAMES = ("tsconfig.json", "jsconfig.json")  # in order of preference within one folder


def _strip_comments(text: str) -> str:
    out: list[str] = []
    i, n, in_string = 0, len(text), False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
            out.append(ch)
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end == -1 else end
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _strip_trailing_commas(text: str) -> str:
    out: list[str] = []
    i, n, in_string = 0, len(text), False
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                out.append(text[i : i + 2])
                i += 2
                continue
            if ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_jsonc(text: str) -> dict | None:
    """JSON with `//` and `/* */` comments and trailing commas. None unless the result is a JSON object."""
    try:
        value = json.loads(_strip_trailing_commas(_strip_comments(text)))
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _inside(path: str) -> str | None:
    """Normalize a joined repository-relative path; None if it leaves the root. The root itself is ""."""
    norm = posixpath.normpath(path) if path else "."
    if norm == ".." or norm.startswith("../") or norm.startswith("/"):
        return None
    return "" if norm == "." else norm


@dataclass(frozen=True)
class Effective:
    """Options that apply to one file. Paths are repository-relative; targets may contain one `*`."""

    base_url: str | None
    paths: tuple[tuple[str, tuple[str, ...]], ...]


_NONE = Effective(None, ())


def _pattern_order(pattern: str) -> tuple[int, int, str]:
    if "*" not in pattern:
        return (0, 0, pattern)
    return (1, -len(pattern.split("*", 1)[0]), pattern)


class Configs:
    def __init__(self, files: frozenset[str], read: Callable[[str], bytes]) -> None:
        self._files = files
        self._read = read
        self._parsed: dict[str, dict | None] = {}
        self._options: dict[str, dict] = {}
        self._by_folder: dict[str, Effective] = {}
        for path in sorted(files):
            if posixpath.basename(path) in CONFIG_NAMES:
                self._merged(path)  # loads the whole `extends` chain now, so `invalid` is complete before any lookup

    @property
    def invalid(self) -> tuple[str, ...]:
        return tuple(sorted(path for path, value in self._parsed.items() if value is None))

    def _load(self, path: str) -> dict | None:
        if path not in self._parsed:
            try:
                text = self._read(path).decode("utf-8-sig")
            except UnicodeDecodeError:
                text = ""
            self._parsed[path] = parse_jsonc(text)
        return self._parsed[path]

    def _extends_targets(self, path: str, raw) -> list[str]:
        entries = raw if isinstance(raw, list) else [raw] if isinstance(raw, str) else []
        folder = posixpath.dirname(path)
        targets = []
        for entry in entries:
            if not isinstance(entry, str) or not entry.startswith("."):
                continue  # package names and absolute paths would need node_modules or the outside world
            joined = _inside(posixpath.join(folder, entry))
            if joined is None:
                continue
            target = next((c for c in (joined, joined + ".json") if c in self._files), None)
            if target is not None:
                targets.append(target)
        return targets

    def _merged(self, path: str, chain: tuple[str, ...] = ()) -> dict:
        """{"baseUrl": repo path, "paths": (mapping, folder of the defining config)} for one config file."""
        if path in self._options:
            return self._options[path]
        config = self._load(path)
        merged: dict = {}
        if config is not None:
            for target in self._extends_targets(path, config.get("extends")):
                if target not in chain and target != path:
                    merged.update(self._merged(target, chain + (path,)))
            options = config.get("compilerOptions")
            if isinstance(options, dict):
                folder = posixpath.dirname(path)
                base_url = options.get("baseUrl")
                if isinstance(base_url, str):
                    anchored = _inside(posixpath.join(folder, base_url))
                    if anchored is not None:
                        merged["baseUrl"] = anchored
                paths = options.get("paths")
                if isinstance(paths, dict):
                    merged["paths"] = (paths, folder)
        if not chain:
            self._options[path] = merged
        return merged

    def _effective(self, config_path: str) -> Effective:
        merged = self._merged(config_path)
        base_url = merged.get("baseUrl")
        mapping, defining_folder = merged.get("paths", ({}, ""))
        anchor = base_url if base_url is not None else defining_folder
        paths = []
        for pattern in sorted(mapping, key=_pattern_order):
            targets = mapping[pattern]
            if not isinstance(targets, list):
                continue
            anchored = [_inside(posixpath.join(anchor, t)) for t in targets if isinstance(t, str)]
            paths.append((pattern, tuple(t for t in anchored if t is not None)))
        return Effective(base_url, tuple(paths))

    def for_file(self, path: str) -> Effective:
        """The nearest valid config in the file's folder or an ancestor inside the root."""
        return self._for_folder(posixpath.dirname(path))

    def _for_folder(self, folder: str) -> Effective:
        if folder not in self._by_folder:
            effective = None
            for name in CONFIG_NAMES:
                candidate = posixpath.join(folder, name)
                if candidate in self._files and self._load(candidate) is not None:
                    effective = self._effective(candidate)
                    break
            if effective is None:
                effective = self._for_folder(posixpath.dirname(folder)) if folder else _NONE
            self._by_folder[folder] = effective
        return self._by_folder[folder]


def load_configs(files: frozenset[str], read: Callable[[str], bytes]) -> Configs:
    return Configs(files, read)
