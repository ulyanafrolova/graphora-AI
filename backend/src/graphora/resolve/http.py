"""The HTTP bridge: frontend calls linked to backend routes by method and normalized path
(specs/015-http-bridge research R1–R5).

Calls are recognized by their form only (`fetch(...)`, `axios.get(...)`): a local function named `fetch` is not
told apart, and a matching URL does not prove the call reaches that route. That is why every HTTP edge is
`heuristic`. Prefixes and base URLs are used only when they are literal strings in the code; anything else is
never guessed: such routes match nothing and such calls are `unresolved`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from graphora.graph.model import Edge, UnresolvedNode
from graphora.graph.serialize import snippet_hash
from graphora.resolve import python as py_resolve

HTTP_VERSION = "0.1.0"
EXTRACTOR = f"http-bridge@{HTTP_VERSION}"
PARAM = "*"
_PARAM_SEGMENT = re.compile(r"\{[^{}]*\}|<[^<>]*>")


def normalize(path: str) -> tuple[str, ...]:
    """Segments of a URL path: query and fragment dropped, empty segments removed, a parameter segment is `*`."""
    path = path.split("#", 1)[0].split("?", 1)[0]
    out = []
    for segment in path.split("/"):
        if not segment:
            continue
        out.append(PARAM if _PARAM_SEGMENT.search(segment) else segment)
    return tuple(out)


def display(segments: tuple[str, ...]) -> str:
    return "/" + "/".join("{}" if s == PARAM else s for s in segments)


@dataclass(frozen=True)
class Route:
    file: str
    methods: tuple[str, ...]
    segments: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class Call:
    file: str
    method: str | None
    segments: tuple[str, ...] | None  # None: dynamic
    line: int
    column: int
    text: str


# --- routes --------------------------------------------------------------------------------------------------


def _from_module(path: str, record: Any, index: py_resolve.ModuleIndex) -> str | None:
    """The absolute dotted module of a `from` import, relative ones included (as `py_resolve.resolve` does)."""
    if record.level == 0:
        return record.module
    package = py_resolve._package_parts(path, index)
    drop = record.level - 1
    if drop > len(package) or len(package) - drop == 0:
        return None
    return ".".join(package[: len(package) - drop] + ([record.module] if record.module else []))


def _locals(path: str, facts: Any, index: py_resolve.ModuleIndex) -> dict[str, tuple[str, str | None]]:
    """Local names bound by imports: name → (file, imported name), imported name None for a module."""
    out: dict[str, tuple[str, str | None]] = {}
    for record in facts.imports:
        if record.kind == "dynamic":
            continue
        targets = py_resolve.resolve(path, record, index)
        for (name, local), target in zip(record.bindings, targets, strict=False):
            if target.kind != "file":
                continue
            file = target.node_id.split(":", 1)[1]
            if record.kind == "import":
                if local != name or "." not in name:
                    out[local] = (file, None)
            elif target.symbol is not None:
                base = _from_module(path, record, index)
                module = index.modules.get(f"{base}.{name}") if base else None
                out[local] = (file, None) if module == file else (file, target.symbol)
    return out


class _Routers:
    """Routers and apps with their mounts, resolved across files."""

    def __init__(self, py_facts: dict[str, Any]) -> None:
        index = py_resolve.build_index(sorted(py_facts))
        self.declared: dict[tuple[str, str], Any] = {}
        self.locals: dict[str, dict[str, tuple[str, str | None]]] = {}
        mounts: dict[tuple[str, str], list[tuple[tuple[str, str], Any]]] = defaultdict(list)
        for path, facts in sorted(py_facts.items()):
            if facts is None:
                continue
            for router in facts.routers:
                self.declared[(path, router.name)] = router
            self.locals[path] = _locals(path, facts, index) if facts.routes or facts.mounts else {}
        for path, facts in sorted(py_facts.items()):
            for mount in facts.mounts if facts is not None else ():
                target = self._name(path, mount.target)
                parent = self._name(path, mount.app)
                if target is not None and parent is not None:
                    mounts[target].append((parent, mount))
        self.mounts = mounts

    def _name(self, path: str, text: str) -> tuple[str, str] | None:
        """(file, name) of a router written as `name` or `module.name` in `path`."""
        if "." in text:
            module, name = text.rsplit(".", 1)
            bound = self.locals.get(path, {}).get(module)
            return (bound[0], name) if bound is not None and bound[1] is None else None
        if (path, text) in self.declared:
            return (path, text)
        bound = self.locals.get(path, {}).get(text)
        return (bound[0], bound[1]) if bound is not None and bound[1] is not None else None

    def prefixes(self, key: tuple[str, str], seen: frozenset[tuple[str, str]] = frozenset()) -> list[str] | None:
        """Every full prefix the router is served under; None when any part is not a literal."""
        router = self.declared.get(key)
        if router is None or router.prefix is None or key in seen:
            return None
        if router.kind == "app":
            return [""]
        parents = self.mounts.get(key, [])
        if not parents:
            return [router.prefix]
        out: list[str] = []
        for parent, mount in parents:
            if mount.prefix is None:
                return None
            above = self.prefixes(parent, seen | {key})
            if above is None:
                return None
            if router.kind == "blueprint":
                own = mount.prefix if mount.given else router.prefix
            else:
                own = mount.prefix + router.prefix
            out.extend(a + own for a in above)
        return sorted(set(out))


def routes(py_facts: dict[str, Any]) -> list[Route]:
    routers = _Routers(py_facts)
    out: list[Route] = []
    for path, facts in sorted(py_facts.items()):
        for fact in facts.routes if facts is not None else ():
            key = routers._name(path, fact.obj)
            prefixes = routers.prefixes(key) if key is not None else None
            for prefix in prefixes or ():
                out.append(Route(path, fact.methods, normalize(prefix + "/" + fact.path), fact.line))
    return sorted(set(out), key=lambda r: (r.file, r.line, r.segments, r.methods))


# --- calls ---------------------------------------------------------------------------------------------------


def call_segments(fact: Any, constants: dict[str, str]) -> tuple[str, ...] | None:
    """The call's path segments, or None when it cannot be read (dynamic)."""
    if fact.parts is None:
        return None
    parts = list(fact.parts)
    if parts and parts[0].kind == "expr":
        if parts[0].value not in constants:
            return None
        parts[0] = type(parts[0])("text", constants[parts[0].value])
    text = "".join(p.value if p.kind == "text" else "{p}" for p in parts)
    if not text.startswith("/"):
        return None
    return normalize(text)


def _is_absolute(fact: Any, constants: dict[str, str]) -> bool:
    if fact.absolute:
        return True
    first = fact.parts[0] if fact.parts else None
    value = constants.get(first.value) if first is not None and first.kind == "expr" else None
    return value is not None and (value.startswith(("http://", "https://", "//")) or "://" in value)


# --- matching ------------------------------------------------------------------------------------------------


def _fits(call: tuple[str, ...], route: tuple[str, ...]) -> bool:
    return len(call) == len(route) and all(c == r or PARAM in (c, r) for c, r in zip(call, route, strict=True))


def _score(call: tuple[str, ...], route: tuple[str, ...]) -> tuple[int, ...]:
    """Per position 2 when call and route have the same form (equal text, or both parameters), 1 when one is a
    parameter and the other text; compared position by position, so `/users/me` wins for a call to `/users/me`
    and `/users/{id}` wins for a call to `/users/${x}`."""
    return tuple(2 if (c == PARAM) == (r == PARAM) else 1 for c, r in zip(call, route, strict=True))


def match(call: Call, candidates: list[Route]) -> tuple[str, Route | None]:
    """("edge", route), or ("dynamic" | "not_found" | "ambiguous", None)."""
    if call.segments is None:
        return "dynamic", None
    fitting = [r for r in candidates if (call.method is None or call.method in r.methods) and _fits(call.segments, r.segments)]
    if not fitting:
        return "not_found", None
    best = max(_score(call.segments, r.segments) for r in fitting)
    winners = sorted((r for r in fitting if _score(call.segments, r.segments) == best), key=lambda r: (r.file, r.line))
    if len({r.file for r in winners}) > 1:
        return "ambiguous", None
    return "edge", winners[0]


class RouteTree:
    """Routes by path segments, so a call meets only the routes its path can fit (research R8): a literal call
    segment follows its own branch and the parameter branch, a parameter follows every branch."""

    def __init__(self, routes: list[Route]) -> None:
        self.root: dict = {}
        for route in routes:
            node = self.root
            for segment in route.segments:
                node = node.setdefault(segment, {})
            node.setdefault(None, []).append(route)

    def candidates(self, segments: tuple[str, ...]) -> list[Route]:
        nodes = [self.root]
        for segment in segments:
            following = []
            for node in nodes:
                if segment == PARAM:
                    following.extend(child for key, child in node.items() if key is not None)
                else:
                    following.extend(node[key] for key in (segment, PARAM) if key in node)
            nodes = following
            if not nodes:
                return []
        return [route for node in nodes for route in node.get(None, ())]


def bridge(py_facts: dict[str, Any], js_facts: dict[str, Any], snapshot: str) -> tuple[list[Edge], list[UnresolvedNode]]:
    """HTTP edges and the unresolved nodes they point to."""
    calls = []
    for path, facts in sorted(js_facts.items()):
        for fact in facts.http_calls if facts is not None else ():
            if _is_absolute(fact, facts.constants):
                continue
            calls.append(Call(path, fact.method, call_segments(fact, facts.constants), fact.line, fact.column, fact.text))
    if not calls:
        return [], []
    tree = RouteTree(routes(py_facts))
    edges: list[Edge] = []
    nodes: dict[str, UnresolvedNode] = {}
    for call in calls:
        kind, route = match(call, tree.candidates(call.segments) if call.segments is not None else [])
        method = call.method or "?"
        symbol = f"{method} {display(call.segments) if call.segments is not None else '?'}"
        common = dict(symbol=symbol, line=call.line, column=call.column, snapshot=snapshot, extractor=EXTRACTOR,
                      snippet_hash=snippet_hash(call.text), type="http_call")
        if route is not None:
            edges.append(Edge(source=f"file:{call.file}", target=f"file:{route.file}", confidence="heuristic",
                              reason="http_route", route_line=route.line, **common))
        else:
            node = UnresolvedNode(symbol, "http")
            nodes[node.id] = node
            edges.append(Edge(source=f"file:{call.file}", target=node.id, confidence="unresolved", reason=kind, **common))
    return edges, [nodes[k] for k in sorted(nodes)]
