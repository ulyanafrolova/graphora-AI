"""FastAPI and Flask route facts for the HTTP bridge: route decorators, router and blueprint declarations, and the
calls that mount them (specs/015-http-bridge research R2). Only literal strings count; nothing is evaluated."""

from __future__ import annotations

from dataclasses import dataclass

from tree_sitter import Node

from graphora.adapters.position import Positions

VERBS = ("get", "post", "put", "patch", "delete", "head", "options")
_CONSTRUCTORS = {"FastAPI": ("app", None), "Flask": ("app", None), "APIRouter": ("router", "prefix"), "Blueprint": ("blueprint", "url_prefix")}
_MOUNTS = {"include_router": "prefix", "register_blueprint": "url_prefix"}


@dataclass(frozen=True)
class RouteFact:
    obj: str
    methods: tuple[str, ...]
    path: str
    line: int
    column: int
    text: str


@dataclass(frozen=True)
class RouterFact:
    name: str
    kind: str  # app | router | blueprint
    prefix: str | None  # "" when absent, None when not a literal string


@dataclass(frozen=True)
class MountFact:
    app: str
    target: str  # a name or `module.name`
    prefix: str | None  # "" when absent (no override), None when not a literal string
    given: bool  # the prefix argument is present
    line: int


def _text(node: Node) -> str:
    return node.text.decode("utf-8", errors="replace")


def literal(node: Node | None) -> str | None:
    """The value of a plain string literal (no f-string, no implicit concatenation), else None."""
    if node is None or node.type != "string":
        return None
    if any(c.type == "interpolation" for c in node.named_children):
        return None
    start = next((c for c in node.children if c.type == "string_start"), None)
    if start is not None and any(ch in _text(start).lower() for ch in "fb"):
        return None
    return "".join(_text(c) for c in node.named_children if c.type in ("string_content", "escape_sequence"))


def _arguments(call: Node) -> tuple[list[Node], dict[str, Node]]:
    args = call.child_by_field_name("arguments")
    positional, keywords = [], {}
    for child in args.named_children if args is not None else []:
        if child.type == "keyword_argument":
            name, value = child.child_by_field_name("name"), child.child_by_field_name("value")
            if name is not None and value is not None:
                keywords[_text(name)] = value
        elif child.type not in ("comment", "list_splat", "dictionary_splat"):
            positional.append(child)
    return positional, keywords


def _methods(node: Node | None) -> tuple[str, ...] | None:
    """Upper-case methods of a literal list or tuple of strings; None when not all literal."""
    if node is None or node.type not in ("list", "tuple"):
        return None
    values = [literal(c) for c in node.named_children]
    if not values or any(v is None for v in values):
        return None
    return tuple(sorted({v.upper() for v in values if v}))


def _route(position: Positions, decorator: Node) -> RouteFact | None:
    call = next((c for c in decorator.named_children if c.type == "call"), None)
    function = call.child_by_field_name("function") if call is not None else None
    if function is None or function.type != "attribute":
        return None
    obj, attr = function.child_by_field_name("object"), function.child_by_field_name("attribute")
    if obj is None or attr is None or obj.type != "identifier":
        return None
    verb = _text(attr)
    positional, keywords = _arguments(call)
    path = literal(positional[0] if positional else keywords.get("path") or keywords.get("rule"))
    if path is None:
        return None
    if verb in VERBS:
        methods: tuple[str, ...] | None = (verb.upper(),)
    elif verb in ("route", "api_route"):
        methods = _methods(keywords["methods"]) if "methods" in keywords else ("GET",)
    else:
        return None
    if methods is None:
        return None
    line, column = position(decorator)
    return RouteFact(_text(obj), methods, path, line, column, _text(decorator))


def _router(statement: Node) -> RouterFact | None:
    assignment = statement.named_children[0] if statement.named_children else None
    if assignment is None or assignment.type != "assignment":
        return None
    left, right = assignment.child_by_field_name("left"), assignment.child_by_field_name("right")
    if left is None or right is None or left.type != "identifier" or right.type != "call":
        return None
    function = right.child_by_field_name("function")
    if function is None:
        return None
    name = _text(function).rsplit(".", 1)[-1]
    if name not in _CONSTRUCTORS:
        return None
    kind, keyword = _CONSTRUCTORS[name]
    prefix: str | None = ""
    if keyword is not None:
        _, keywords = _arguments(right)
        if keyword in keywords:
            prefix = literal(keywords[keyword])
    return RouterFact(_text(left), kind, prefix)


def _mount(position: Positions, call: Node) -> MountFact | None:
    function = call.child_by_field_name("function")
    if function is None or function.type != "attribute":
        return None
    obj, attr = function.child_by_field_name("object"), function.child_by_field_name("attribute")
    if obj is None or attr is None or obj.type != "identifier" or _text(attr) not in _MOUNTS:
        return None
    positional, keywords = _arguments(call)
    if not positional or positional[0].type not in ("identifier", "attribute"):
        return None
    keyword = _MOUNTS[_text(attr)]
    given = keyword in keywords
    prefix = literal(keywords[keyword]) if given else ""
    return MountFact(_text(obj), _text(positional[0]), prefix, given, position(call)[0])


def facts(
    position: Positions, root: Node, decorators: list[Node], calls: list[Node]
) -> tuple[tuple[RouteFact, ...], tuple[RouterFact, ...], tuple[MountFact, ...]]:
    """From the decorators and calls the extractor's single walk collected, in source order (no second walk)."""
    routes = [r for r in (_route(position, d) for d in decorators) if r is not None]
    routers = [r for r in (_router(c) for c in root.named_children if c.type == "expression_statement") if r is not None]
    mounts = [m for m in (_mount(position, c) for c in calls) if m is not None]
    return tuple(routes), tuple(routers), tuple(mounts)
