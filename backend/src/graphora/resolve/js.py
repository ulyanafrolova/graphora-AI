"""Rule-based TS/JS specifier resolution (specs/003-ts-js-analysis/data-model.md § Resolution).

Candidates are only walked, non-skipped files, so nothing outside the root or in `node_modules` is read.
Anything the rules cannot prove is unresolved.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Callable
from importlib import resources

from graphora.adapters.js.extract import ImportRecord
from graphora.resolve.tsconfig import Configs

RESOLVER_VERSION = "0.2.0"  # 0.2.0: `.`, `..` and a trailing `/` resolve to a folder index only
BUILTINS_VERSION = "26.0.0"

EXTENSIONS = (".ts", ".tsx", ".d.ts", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".json")
TS_FOR_JS = {".js": (".ts", ".tsx", ".d.ts"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
_URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def _load_builtins() -> tuple[frozenset[str], frozenset[str]]:
    """(bare top-level names, prefix-only names such as `node:test`)."""
    text = resources.files("graphora.resolve").joinpath("data/node_builtins.txt").read_text(encoding="utf-8")
    names = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    return frozenset(n for n in names if not n.startswith("node:")), frozenset(n for n in names if n.startswith("node:"))


BUILTINS, PREFIX_ONLY = _load_builtins()


def category(name: str) -> str:
    """`builtin` for Node built-ins (prefix-only ones keep their `node:` prefix in the name), else `third_party`."""
    return "builtin" if name in BUILTINS or name in PREFIX_ONLY else "third_party"


def _inside(path: str) -> str | None:
    norm = posixpath.normpath(path) if path else "."
    if norm == ".." or norm.startswith("../") or norm.startswith("/"):
        return None
    return "" if norm == "." else norm


def _package_name(specifier: str) -> str | None:
    parts = specifier.split("/")
    if specifier.startswith("@"):
        if len(parts) < 2 or parts[0] == "@" or not parts[1]:
            return None
        return f"{parts[0]}/{parts[1]}"
    return parts[0] or None


def _match(pattern: str, specifier: str) -> str | None:
    """The text matched by `*`, "" for an exact pattern, or None if the pattern does not match."""
    if "*" not in pattern:
        return "" if pattern == specifier else None
    prefix, suffix = pattern.split("*", 1)
    if specifier.startswith(prefix) and specifier.endswith(suffix) and len(specifier) >= len(prefix) + len(suffix):
        return specifier[len(prefix) : len(specifier) - len(suffix)]
    return None


def workspace_names(files: frozenset[str], read: Callable[[str], bytes]) -> frozenset[str]:
    """`name` of every package.json below the root. Invalid files contribute nothing (data-model.md § Resolution)."""
    names = set()
    for path in files:
        if posixpath.basename(path) != "package.json" or path == "package.json":
            continue
        try:
            data = json.loads(read(path).decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("name"), str) and data["name"]:
            names.add(data["name"])
    return frozenset(names)


class JsResolver:
    def __init__(self, files: frozenset[str], analyzed: frozenset[str], configs: Configs, workspaces: frozenset[str]) -> None:
        self._files = files
        self._analyzed = analyzed
        self._configs = configs
        self._workspaces = workspaces
        self._tried: dict[tuple[str, bool], str | None] = {}

    def _try(self, p: str, folder_only: bool = False) -> str | None:
        """The first existing file for path `p` (data-model.md § Trying a path); only step 4 when `folder_only`."""
        key = (p, folder_only)
        if key not in self._tried:
            candidates = []
            if p and not folder_only:
                candidates += [p] + [p + ext for ext in EXTENSIONS]
                ext = posixpath.splitext(p)[1]
                candidates += [p[: -len(ext)] + ts for ts in TS_FOR_JS.get(ext, ())]
            index = posixpath.join(p, "index") if p else "index"
            candidates += [index + e for e in EXTENSIONS]
            self._tried[key] = next((c for c in candidates if c in self._files), None)
        return self._tried[key]

    def _target(self, hit: str) -> str:
        return f"file:{hit}" if hit in self._analyzed else f"asset:{hit}"

    def resolve(self, path: str, record: ImportRecord) -> tuple[str, str | None]:
        """(target node id, unresolved reason or None) for one record found in file `path`."""
        specifier = record.specifier
        if specifier is None:
            return f"unresolved:npm:{record.text}", "dynamic"
        if specifier in (".", "..") or specifier.startswith(("./", "../")):
            joined = _inside(posixpath.join(posixpath.dirname(path), specifier))
            if joined is None:
                return f"unresolved:npm:{specifier}", "not_found"
            # `.`, `..`, `../..` and a trailing `/` name a folder, as in Node and TypeScript
            folder_only = specifier.endswith("/") or posixpath.basename(specifier) in (".", "..")
            hit = self._try(joined, folder_only)
            return (self._target(hit), None) if hit else (f"unresolved:npm:{joined or '.'}", "not_found")
        if specifier.startswith("node:"):
            top = specifier[5:].split("/")[0]
            if top in BUILTINS:
                return f"ext:npm:{top}", None
            if f"node:{top}" in PREFIX_ONLY:
                return f"ext:npm:node:{top}", None
            return f"unresolved:npm:{specifier}", "not_found"
        if specifier.startswith(("/", "#")) or _URL.match(specifier):
            return f"unresolved:npm:{specifier}", "not_found"
        return self._bare(path, specifier, record.text)

    def _bare(self, path: str, specifier: str, text: str) -> tuple[str, str | None]:
        effective = self._configs.for_file(path)
        for pattern, targets in effective.paths:
            star = _match(pattern, specifier)
            if star is None:
                continue
            for target in targets:
                candidate = _inside(target.replace("*", star, 1))
                hit = self._try(candidate) if candidate is not None else None
                if hit:
                    return self._target(hit), None
            return f"unresolved:npm:{specifier}", "not_found"
        if effective.base_url is not None:
            candidate = _inside(posixpath.join(effective.base_url, specifier))
            hit = self._try(candidate) if candidate else None
            if hit:
                return self._target(hit), None
        package = _package_name(specifier)
        if package is None:
            return f"unresolved:npm:{specifier or text}", "not_found"
        if package in self._workspaces:
            return f"unresolved:npm:{specifier}", "workspace_package"
        top = specifier.split("/")[0]
        if top in BUILTINS:
            return f"ext:npm:{top}", None
        return f"ext:npm:{package}", None
