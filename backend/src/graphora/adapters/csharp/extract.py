"""Extract namespaces, type and method definitions and `using` directives from C# with Tree-sitter. Never runs or
compiles the code.

Node types and fields are listed in specs/007-csharp-analysis/research.md § R1; the records are described in
data-model.md § Internal entities.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import tree_sitter_c_sharp
from tree_sitter import Language, Node, Parser

from graphora.adapters.position import CHECK_EVERY, Positions, normalize_newlines
from graphora.graph.model import Definition

_PARSER = Parser(Language(tree_sitter_c_sharp.language()))
_BOM = b"\xef\xbb\xbf"

_TYPE_KINDS = {
    "class_declaration": "class",
    "struct_declaration": "struct",
    "record_declaration": "record",
    "record_struct_declaration": "record",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "delegate_declaration": "delegate",
}
_NAMESPACES = ("namespace_declaration", "file_scoped_namespace_declaration")
_NAME_TARGETS = ("identifier", "qualified_name", "generic_name", "alias_qualified_name")


@dataclass(frozen=True)
class TypeDecl:
    """A declared type. `name` is fully qualified (namespace + enclosing types + name)."""

    kind: str
    name: str
    namespace: str  # "" for the global namespace
    line: int
    partial: bool


@dataclass(frozen=True)
class UsingRecord:
    """One `using` directive.

    `target` is the name as written without `global::` and generic arguments; None when the directive aliases a
    type that is not a name (tuple, array, pointer, keyword type), which makes no edge.
    """

    form: Literal["using", "using_static", "using_alias"]
    global_using: bool
    alias: str | None
    target: str | None
    rooted: bool  # written with `global::`: no lookup relative to the enclosing namespace
    namespace: str  # enclosing namespace of the directive, "" at file level
    text: str
    line: int
    column: int


@dataclass(frozen=True)
class CsFacts:
    namespaces: tuple[str, ...]  # every declared namespace, sorted, without ""
    types: tuple[TypeDecl, ...]
    definitions: tuple[Definition, ...]
    usings: tuple[UsingRecord, ...]
    has_error: bool


def _text(node: Node) -> str:
    return node.text.decode("utf-8", errors="replace")


def _has_token(node: Node, token: str) -> bool:
    return any(c.type == token and not c.is_named for c in node.children)


def _name_text(node: Node) -> tuple[str, bool]:
    """A qualified name without whitespace, `global::` or generic arguments, and whether it had `global::`."""
    if node.type == "identifier":
        return _text(node), False
    if node.type == "generic_name":
        ident = next((c for c in node.named_children if c.type == "identifier"), None)
        return (_text(ident) if ident is not None else _text(node).split("<", 1)[0].strip()), False
    if node.type == "alias_qualified_name":
        alias = node.child_by_field_name("alias")
        name = node.child_by_field_name("name")
        inner, _ = _name_text(name) if name is not None else ("", False)
        return inner, alias is not None and _text(alias) == "global"
    if node.type == "qualified_name":
        parts = [c for c in node.named_children if c.type in _NAME_TARGETS]
        if not parts:
            return "".join(_text(node).split()), False
        texts = [_name_text(p) for p in parts]
        rooted = texts[0][1]
        return ".".join(t for t, _ in texts if t), rooted
    return "".join(_text(node).split()), False


def _join(*parts: str) -> str:
    return ".".join(p for p in parts if p)


def _is_partial(node: Node) -> bool:
    return any(c.type == "modifier" and _text(c) == "partial" for c in node.children)


def _using(position: Positions, node: Node, namespace: str) -> UsingRecord:
    alias_node = node.child_by_field_name("name")
    alias = _text(alias_node) if alias_node is not None else None
    target_node = next(
        (c for c in node.named_children if c != alias_node and c.type not in ("comment",)),
        None,
    )
    target: str | None = None
    rooted = False
    if target_node is not None and target_node.type in _NAME_TARGETS:
        target, rooted = _name_text(target_node)
    if alias is not None:
        form: Literal["using", "using_static", "using_alias"] = "using_alias"
    elif _has_token(node, "static"):
        form = "using_static"
    else:
        form = "using"
    line, column = position(node)
    return UsingRecord(form, _has_token(node, "global"), alias, target or None, rooted, namespace, _text(node), line, column)


def extract(source: bytes, check: Callable[[], None] = lambda: None) -> CsFacts | None:
    """Parse one C# file. None if it is not valid UTF-8 (a leading BOM is allowed).

    `check` is called every few thousand nodes, so a time limit can stop work inside one large file."""
    source = source.removeprefix(_BOM)
    try:
        source.decode("utf-8")
    except UnicodeDecodeError:
        return None
    source = normalize_newlines(source)
    root = _PARSER.parse(source).root_node
    position = Positions(source)

    namespaces: set[str] = set()
    types: list[TypeDecl] = []
    definitions: list[Definition] = []
    usings: list[UsingRecord] = []

    # Depth-first in source order, so `Positions` sees nodes in order. Each entry: node, namespace, enclosing types.
    stack: list[tuple[Node, str, str]] = [(root, "", "")]
    seen = 0
    file_namespace = ""
    while stack:
        node, namespace, outer = stack.pop()
        seen += 1
        if seen % CHECK_EVERY == 0:
            check()
        kind = node.type
        children_namespace, children_outer = namespace, outer
        if kind in _NAMESPACES:
            name_node = node.child_by_field_name("name")
            name = _name_text(name_node)[0] if name_node is not None else ""
            children_namespace = _join(namespace, name)
            if children_namespace:
                namespaces.add(children_namespace)
            if kind == "file_scoped_namespace_declaration":
                # The rest of the file (later siblings) belongs to this namespace.
                file_namespace = children_namespace
        elif kind == "using_directive":
            usings.append(_using(position, node, namespace or file_namespace))
            continue
        elif kind in _TYPE_KINDS:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                effective_namespace = namespace or file_namespace
                full = _join(effective_namespace, outer, _text(name_node))
                line = name_node.start_point.row + 1
                types.append(TypeDecl(_TYPE_KINDS[kind], full, effective_namespace, line, _is_partial(node)))
                definitions.append(Definition(_TYPE_KINDS[kind], full, line))
                children_outer = _join(outer, _text(name_node))
                children_namespace = effective_namespace
        elif kind == "method_declaration" and outer:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                definitions.append(Definition("method", _join(namespace or file_namespace, outer, _text(name_node)), name_node.start_point.row + 1))
            continue  # local functions and lambdas inside a body are not definitions
        if kind in ("block", "arrow_expression_clause"):
            continue
        for child in reversed(node.children):
            stack.append((child, children_namespace, children_outer))

    return CsFacts(
        namespaces=tuple(sorted(namespaces)),
        types=tuple(types),
        definitions=tuple(sorted(definitions, key=lambda d: (d.line, d.name))),
        usings=tuple(usings),
        has_error=root.has_error,
    )
