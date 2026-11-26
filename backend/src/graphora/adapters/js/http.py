"""`fetch` and `axios` call facts for the HTTP bridge, and top-level string constants (specs/015-http-bridge
research R3). A call is recognized by its form only; the URL is kept as literal pieces and expressions."""

from __future__ import annotations

import re
from dataclasses import dataclass

from tree_sitter import Node

from graphora.adapters.position import Positions

_AXIOS_VERBS = ("get", "post", "put", "patch", "delete", "head", "options")
_GLOBALS = ("window", "globalThis", "self")
_ABSOLUTE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:)?//")  # a scheme or `//` at the very start: another host


@dataclass(frozen=True)
class Part:
    kind: str  # text | expr
    value: str | None  # the text, or an expression's identifier name (None for any other expression)


@dataclass(frozen=True)
class HttpCallFact:
    method: str | None  # None when not a literal
    parts: tuple[Part, ...] | None  # None for a URL that is not a string, template or concatenation
    absolute: bool
    line: int
    column: int
    text: str


def is_absolute(url: str) -> bool:
    return _ABSOLUTE.match(url) is not None


def _text(node: Node) -> str:
    return node.text.decode("utf-8", errors="replace")


def string_value(node: Node | None) -> str | None:
    """A plain string literal's value, or a template literal without substitutions."""
    if node is None:
        return None
    if node.type == "string":
        return "".join(_text(c) for c in node.named_children if c.type in ("string_fragment", "escape_sequence"))
    if node.type == "template_string" and not any(c.type == "template_substitution" for c in node.named_children):
        return "".join(_text(c) for c in node.named_children if c.type in ("string_fragment", "escape_sequence"))
    return None


def _expr(node: Node) -> Part:
    return Part("expr", _text(node) if node.type == "identifier" else None)


def _parts(node: Node) -> list[Part] | None:
    value = string_value(node)
    if value is not None:
        return [Part("text", value)]
    if node.type == "template_string":
        out = []
        for child in node.named_children:
            if child.type in ("string_fragment", "escape_sequence"):
                out.append(Part("text", _text(child)))
            elif child.type == "template_substitution":
                inner = child.named_children[0] if child.named_children else None
                out.append(_expr(inner) if inner is not None else Part("expr", None))
        return out
    if node.type == "binary_expression" and node.child_by_field_name("operator") is not None:
        if _text(node.child_by_field_name("operator")) != "+":
            return None
        left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
        lp = _parts(left) if left is not None else None
        rp = _parts(right) if right is not None else None
        out = (lp if lp is not None else [_expr(left)]) + (rp if rp is not None else [_expr(right)])
        return out if any(p.kind == "text" for p in out) else None
    if node.type == "parenthesized_expression" and node.named_children:
        return _parts(node.named_children[0])
    return None


def _merged(parts: list[Part]) -> tuple[Part, ...]:
    out: list[Part] = []
    for p in parts:
        if p.kind == "text" and out and out[-1].kind == "text":
            out[-1] = Part("text", (out[-1].value or "") + (p.value or ""))
        elif not (p.kind == "text" and not p.value):
            out.append(p)
    return tuple(out)


def _object(node: Node | None) -> dict[str, Node] | None:
    if node is None or node.type != "object":
        return None
    out = {}
    for pair in node.named_children:
        if pair.type == "pair":
            key, value = pair.child_by_field_name("key"), pair.child_by_field_name("value")
            if key is not None and value is not None:
                name = string_value(key) if key.type == "string" else _text(key)
                if name is not None:
                    out[name] = value
        elif pair.type == "shorthand_property_identifier":
            out[_text(pair)] = pair
    return out


def _method(options: dict[str, Node] | None, default: str) -> str | None:
    if options is None or "method" not in options:
        return default
    value = string_value(options["method"])
    return value.upper() if value else None


def _call(position: Positions, node: Node) -> HttpCallFact | None:
    function = node.child_by_field_name("function")
    arguments = node.child_by_field_name("arguments")
    if function is None or arguments is None:
        return None
    args = [a for a in arguments.named_children if a.type != "comment"]
    name = _text(function)
    url: Node | None
    if name == "fetch" or (function.type == "member_expression" and name.split(".")[0] in _GLOBALS and name.endswith(".fetch")):
        url = args[0] if args else None
        method = _method(_object(args[1]) if len(args) > 1 else None, "GET")
    elif function.type == "member_expression" and name.startswith("axios.") and name.count(".") == 1:
        verb = name.split(".", 1)[1]
        if verb in _AXIOS_VERBS:
            url, method = (args[0] if args else None), verb.upper()
        elif verb == "request":
            config = _object(args[0]) if args else None
            url, method = (config or {}).get("url"), _method(config, "GET")
        else:
            return None
    elif name == "axios":
        first = _object(args[0]) if args else None
        if first is not None:
            url, method = first.get("url"), _method(first, "GET")
        else:
            url, method = (args[0] if args else None), _method(_object(args[1]) if len(args) > 1 else None, "GET")
    else:
        return None
    parts = _parts(url) if url is not None else None
    merged = _merged(parts) if parts is not None else None
    first_text = merged[0].value if merged and merged[0].kind == "text" else ""
    absolute = is_absolute(first_text or "")
    line, column = position(node)
    return HttpCallFact(method, merged, absolute, line, column, _text(node))


def calls(position: Positions, call_nodes: list[Node]) -> tuple[HttpCallFact, ...]:
    """From the call expressions the extractor's single walk collected (no second walk)."""
    out = [f for f in (_call(position, n) for n in call_nodes) if f is not None]
    return tuple(sorted(out, key=lambda f: (f.line, f.column)))


def constants(root: Node) -> dict[str, str]:
    """Top-level `const NAME = "<literal>"` (also when exported)."""
    out: dict[str, str] = {}
    for child in root.named_children:
        declaration = child
        if child.type == "export_statement":
            declaration = child.child_by_field_name("declaration") or child
        if declaration.type != "lexical_declaration" or not _text(declaration).startswith("const"):
            continue
        for declarator in declaration.named_children:
            if declarator.type != "variable_declarator":
                continue
            name, value = declarator.child_by_field_name("name"), declarator.child_by_field_name("value")
            text = string_value(value)
            if name is not None and name.type == "identifier" and text is not None:
                out[_text(name)] = text
    return dict(sorted(out.items()))
