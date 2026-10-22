"""Rule-based Python import resolution (data-model.md § Resolution). Anything the rules cannot prove is unresolved."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

from graphora.adapters.python.extract import ImportRecord

RESOLVER_VERSION = "0.1.0"
STDLIB_VERSION = "3.14.0"
ROOTS = ("", "src")
_SUFFIX_RANK = {".py": 0, ".pyi": 1}


def _load_stdlib() -> frozenset[str]:
    text = resources.files("graphora.resolve").joinpath("data/stdlib_modules.txt").read_text(encoding="utf-8")
    return frozenset(line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#"))


STDLIB = _load_stdlib()


@dataclass(frozen=True)
class Target:
    """Where one imported name points: a node id plus the edge's symbol and, if unresolved, its reason."""

    node_id: str
    symbol: str | None
    reason: str | None = None

    @property
    def kind(self) -> str:
        return self.node_id.split(":", 1)[0]


@dataclass(frozen=True)
class ModuleIndex:
    modules: dict[str, str]
    namespaces: frozenset[str]
    has_src: bool

    def is_local(self, dotted: str) -> bool:
        top = dotted.split(".")[0]
        return top in self.modules or top in self.namespaces


def _split(path: str) -> tuple[list[str], str] | None:
    for suffix in _SUFFIX_RANK:
        if path.endswith(suffix):
            return path[: -len(suffix)].split("/"), suffix
    return None


def build_index(paths: list[str]) -> ModuleIndex:
    has_src = any(p.startswith("src/") for p in paths)
    modules: dict[str, str] = {}
    namespaces: set[str] = set()
    for root in ROOTS:
        if root == "src" and not has_src:
            continue
        candidates: dict[str, tuple[int, str]] = {}
        dirs: set[str] = set()
        packages: set[str] = set()
        for path in sorted(paths):
            if root and not path.startswith(root + "/"):
                continue
            split = _split(path[len(root) + 1 :] if root else path)
            if split is None:
                continue
            parts, suffix = split
            dir_parts = parts[:-1]
            if parts[-1] == "__init__":
                parts = parts[:-1]
                if parts and all(p.isidentifier() for p in parts):
                    packages.add(".".join(parts))
            if not parts or not all(p.isidentifier() for p in parts):
                continue
            dotted = ".".join(parts)
            rank = _SUFFIX_RANK[suffix]
            if dotted not in candidates or rank < candidates[dotted][0]:
                candidates[dotted] = (rank, path)
            for i in range(1, len(dir_parts) + 1):
                dirs.add(".".join(dir_parts[:i]))
        for dotted, (_, path) in candidates.items():
            modules.setdefault(dotted, path)
        namespaces |= dirs - packages
    return ModuleIndex(modules, frozenset(namespaces - set(modules)), has_src)


def _package_parts(path: str, index: ModuleIndex) -> list[str]:
    rel = path[len("src/") :] if index.has_src and path.startswith("src/") else path
    split = _split(rel)
    parts = split[0] if split else rel.split("/")
    return parts[:-1]


def _external(dotted: str, symbol: str | None) -> Target:
    top = dotted.split(".")[0]
    return Target(f"ext:{top}", symbol)


def category(name: str) -> str:
    return "stdlib" if name in STDLIB else "third_party"


def _import_target(dotted: str, index: ModuleIndex) -> Target:
    """`import a.b.c`: the full dotted name must exist; no fallback to a parent module."""
    if dotted in index.modules:
        return Target(f"file:{index.modules[dotted]}", None)
    if dotted in index.namespaces:
        return Target(f"unresolved:{dotted}", None, "namespace_package")
    if index.is_local(dotted):
        return Target(f"unresolved:{dotted}", None, "not_found")
    return _external(dotted, None)


def _from_target(module: str, name: str, index: ModuleIndex, relative: bool) -> Target:
    if name != "*" and f"{module}.{name}" in index.modules:
        return Target(f"file:{index.modules[f'{module}.{name}']}", name)
    if module in index.modules:
        return Target(f"file:{index.modules[module]}", name)
    if module in index.namespaces:
        reference = module if name == "*" else f"{module}.{name}"
        return Target(f"unresolved:{reference}", name, "not_found")
    if relative or index.is_local(module):
        return Target(f"unresolved:{module}", name, "not_found")
    return _external(module, name)


def resolve(path: str, record: ImportRecord, index: ModuleIndex) -> list[Target]:
    """One target per imported name of `record`, found in file `path`."""
    if record.kind == "dynamic":
        if not record.literal or record.module is None:
            return [Target(f"unresolved:{record.text}", None, "dynamic")]
        return [_import_target(record.module, index)]
    if record.kind == "import":
        return [_import_target(record.module, index)]

    if record.level == 0:
        return [_from_target(record.module, name, index, relative=False) for name in record.names]

    package = _package_parts(path, index)
    drop = record.level - 1
    if drop > len(package) or len(package) - drop == 0:
        return [Target(f"unresolved:{record.module_text}", name, "relative_beyond_top") for name in record.names]
    base = package[: len(package) - drop]
    module = ".".join(base + ([record.module] if record.module else []))
    return [_from_target(module, name, index, relative=True) for name in record.names]
