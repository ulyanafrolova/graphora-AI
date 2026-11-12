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
_WRAPPED_TYPES = ("nullable_type", "array_type", "pointer_type", "ref_type", "scoped_type")
_TYPE_FIELDS = frozenset({"type", "returns"})
_NOT_TYPES = frozenset({"var", "dynamic", "nameof", "unmanaged", "notnull"})
# Fields whose identifier declares a name (local, parameter, field, property...): such a name is not a type qualifier.
_DECLARING = frozenset(
    {
        "variable_declarator",
        "parameter",
        "property_declaration",
        "catch_declaration",
        "declaration_pattern",
        "foreach_statement",
        "single_variable_designation",
        "event_declaration",
    }
)


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
class TypeRef:
    """One type name written in code (specs/008-csharp-type-references research.md § R1).

    `kind`: `type` (a type position), `attribute` (also tried with an `Attribute` suffix) or `qualifier` (the left
    part of `X.Member` or a `nameof` argument: counts only if it resolves, never as missing)."""

    name: str  # dotted, without `global::` and generic arguments
    rooted: bool
    kind: Literal["type", "attribute", "qualifier"]
    namespace: str  # innermost enclosing namespace, "" at file level
    line: int
    column: int
    text: str  # the source line, trimmed


@dataclass(frozen=True)
class CsFacts:
    namespaces: tuple[str, ...]  # every declared namespace, sorted, without ""
    types: tuple[TypeDecl, ...]
    definitions: tuple[Definition, ...]
    usings: tuple[UsingRecord, ...]
    has_error: bool
    type_refs: tuple[TypeRef, ...] = ()


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


def _type_params(node: Node) -> frozenset[str]:
    out: set[str] = set()
    for child in node.named_children:
        if child.type == "type_parameter_list":
            for p in child.named_children:
                name = p.child_by_field_name("name") or next((c for c in p.named_children if c.type == "identifier"), None)
                if name is not None:
                    out.add(_text(name))
    return frozenset(out)


class _Refs:
    """Collects type references of one file in source order."""

    def __init__(self, source: bytes, position: Positions) -> None:
        self.lines = source.decode("utf-8").split("\n")
        self.position = position
        self.out: list[TypeRef] = []
        self.qualifiers: list[tuple[list[str], int, int, str, str]] = []  # filtered against declared names at the end

    def _line(self, row: int) -> str:
        return self.lines[row].strip() if row < len(self.lines) else ""

    def type_node(self, node: Node, namespace: str, params: frozenset[str], kind: str = "type") -> None:
        """A node in a type position: emit its name and recurse into generic arguments and element types."""
        t = node.type
        if t in _WRAPPED_TYPES:
            inner = node.child_by_field_name("type") or next((c for c in node.named_children), None)
            if inner is not None:
                self.type_node(inner, namespace, params, kind)
            return
        if t == "tuple_type":
            for element in node.named_children:
                inner = element.child_by_field_name("type")
                if inner is not None:
                    self.type_node(inner, namespace, params)
            return
        if t not in _NAME_TARGETS:
            return
        name, rooted = _name_text(node)
        if name and name not in _NOT_TYPES and name not in params:
            line, column = self.position(node)
            self.out.append(TypeRef(name, rooted, kind, namespace, line, column, self._line(node.start_point.row)))  # type: ignore[arg-type]
        stack = [node]
        while stack:  # generic arguments anywhere inside the name, e.g. A.B<C>.D<E>
            n = stack.pop()
            for c in n.named_children:
                if c.type == "type_argument_list":
                    for arg in c.named_children:
                        self.type_node(arg, namespace, params)
                elif c.type in _NAME_TARGETS:
                    stack.append(c)

    def qualifier(self, node: Node, namespace: str, params: frozenset[str], include_last: bool = False) -> None:
        """`A.B.C.Member` → candidates `A`, `A.B`, `A.B.C` (names only, from the left). For a `nameof` argument the last
        part is a candidate too."""
        parts: list[Node] = []
        n: Node | None = node
        while n is not None and n.type == "member_access_expression":
            name = n.child_by_field_name("name")
            if name is None:
                return
            parts.append(name)
            n = n.child_by_field_name("expression")
        if n is None or n.type not in ("identifier", "generic_name"):
            return
        names = [n, *reversed(parts)]
        if not include_last:
            names = names[:-1]
        texts: list[str] = []
        for p in names:
            if p.type not in ("identifier", "generic_name"):
                break
            texts.append(_name_text(p)[0])
        if not texts or texts[0] in params or texts[0] in _NOT_TYPES:
            return
        line, column = self.position(n)
        self.qualifiers.append((texts, line, column, namespace, self._line(n.start_point.row)))

    def finish(self, declared: set[str]) -> tuple[TypeRef, ...]:
        for texts, line, column, namespace, text in self.qualifiers:
            if texts[0] in declared:
                continue
            for i in range(1, len(texts) + 1):
                self.out.append(TypeRef(".".join(texts[:i]), False, "qualifier", namespace, line, column, text))
        return tuple(self.out)


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
    refs = _Refs(source, position)

    namespaces: set[str] = set()
    types: list[TypeDecl] = []
    definitions: list[Definition] = []
    usings: list[UsingRecord] = []
    declared: set[str] = set()

    # Depth-first in source order. Each entry: node, namespace, enclosing types, type parameters in scope.
    stack: list[tuple[Node, str, str, frozenset[str]]] = [(root, "", "", frozenset())]
    seen = 0
    file_namespace = ""
    while stack:
        node, namespace, outer, params = stack.pop()
        seen += 1
        if seen % CHECK_EVERY == 0:
            check()
        kind = node.type
        namespace = namespace or file_namespace
        children_namespace, children_outer, children_params = namespace, outer, params
        if kind in _NAMESPACES:
            name_node = node.child_by_field_name("name")
            name = _name_text(name_node)[0] if name_node is not None else ""
            children_namespace = _join(namespace if kind == "namespace_declaration" else "", name)
            if children_namespace:
                namespaces.add(children_namespace)
            if kind == "file_scoped_namespace_declaration":
                # The rest of the file (later siblings) belongs to this namespace.
                file_namespace = children_namespace
                continue
        elif kind == "using_directive":
            usings.append(_using(position, node, namespace))
            continue
        elif kind in _TYPE_KINDS:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                full = _join(namespace, outer, _text(name_node))
                line = name_node.start_point.row + 1
                types.append(TypeDecl(_TYPE_KINDS[kind], full, namespace, line, _is_partial(node)))
                definitions.append(Definition(_TYPE_KINDS[kind], full, line))
                children_outer = _join(outer, _text(name_node))
            children_params = params | _type_params(node)
        elif kind == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None and outer:
                definitions.append(Definition("method", _join(namespace, outer, _text(name_node)), name_node.start_point.row + 1))
            children_params = params | _type_params(node)
        elif kind == "local_function_statement":
            children_params = params | _type_params(node)
        elif kind == "member_access_expression" and (node.parent is None or node.parent.type != "member_access_expression"):
            refs.qualifier(node, namespace, params)
        elif kind == "invocation_expression":
            function = node.child_by_field_name("function")
            if function is not None and function.type == "identifier" and _text(function) == "nameof":
                for arg in (a for c in node.named_children if c.type == "argument_list" for a in c.named_children):
                    expr = next((c for c in arg.named_children), None)
                    if expr is not None and expr.type == "identifier":  # `nameof(A.B)` is an ordinary member access
                        refs.qualifier(expr, namespace, params, include_last=True)
        if kind in _DECLARING:
            for field in ("name", "left"):
                n = node.child_by_field_name(field)
                if n is not None and n.type == "identifier":
                    declared.add(_text(n))

        children = []
        for i, child in enumerate(node.children):
            field = node.field_name_for_child(i)
            if field in _TYPE_FIELDS and child.is_named:
                refs.type_node(child, children_namespace, children_params)
                continue
            if field == "right" and kind in ("as_expression", "is_expression"):
                refs.type_node(child, children_namespace, children_params)
                continue
            if kind in ("base_list", "type_argument_list") and child.is_named:
                inner = child.child_by_field_name("type") if child.type == "primary_constructor_base_type" else child
                if inner is not None:
                    refs.type_node(inner, children_namespace, children_params)
                if child.type == "primary_constructor_base_type":
                    children.append(child)  # its argument list may hold more code
                continue
            if kind == "attribute" and field == "name":
                refs.type_node(child, children_namespace, children_params, "attribute")
                continue
            children.append(child)
        for child in reversed(children):
            stack.append((child, children_namespace, children_outer, children_params))

    return CsFacts(
        namespaces=tuple(sorted(namespaces)),
        types=tuple(types),
        definitions=tuple(sorted(definitions, key=lambda d: (d.line, d.name))),
        usings=tuple(usings),
        has_error=root.has_error,
        type_refs=refs.finish(declared),
    )
