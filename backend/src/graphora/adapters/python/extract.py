"""Extract imports and definitions from Python source with Tree-sitter. Never imports or runs the code."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import tree_sitter_python
from tree_sitter import Language, Node, Parser

from graphora.adapters.position import CHECK_EVERY, Positions, normalize_newlines
from graphora.graph.model import Definition

_PARSER = Parser(Language(tree_sitter_python.language()))
_LITERAL_PREFIXES = frozenset("rRuU")


@dataclass(frozen=True)
class ImportRecord:
    """One imported module. `names` is [None] for `import x` and dynamic imports, else the imported names."""

    kind: Literal["import", "from", "dynamic"]
    module: str | None
    level: int
    names: tuple[str | None, ...]
    literal: bool
    text: str
    line: int
    column: int
    module_text: str = ""
    bindings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class FileFacts:
    imports: tuple[ImportRecord, ...]
    definitions: tuple[Definition, ...]
    has_error: bool


def _text(node: Node) -> str:
    return node.text.decode("utf-8", errors="replace")


def _dotted(node: Node) -> str:
    return _text(node.child_by_field_name("name") if node.type == "aliased_import" else node)


def _local_name(node: Node, default: str) -> str:
    """The name an import binds locally: its `as` alias, or the given default."""
    alias = node.child_by_field_name("alias") if node.type == "aliased_import" else None
    return _text(alias) if alias is not None else default


def _import_statement(position: Positions, node: Node) -> list[ImportRecord]:
    line, column = position(node)
    text = _text(node)
    records = []
    for name_node in node.children_by_field_name("name"):
        module = _dotted(name_node)
        binding = ((module, _local_name(name_node, module.split(".")[0])),)
        records.append(ImportRecord("import", module, 0, (None,), True, text, line, column, module, binding))
    return records


def _from_statement(position: Positions, node: Node) -> ImportRecord:
    line, column = position(node)
    if node.type == "future_import_statement":
        module_text, module, level = "__future__", "__future__", 0
    else:
        module_node = node.child_by_field_name("module_name")
        module_text = _text(module_node)
        if module_node.type == "relative_import":
            prefix = next((c for c in module_node.children if c.type == "import_prefix"), None)
            level = len(_text(prefix)) if prefix is not None else 0
            dotted = next((c for c in module_node.children if c.type == "dotted_name"), None)
            module = _text(dotted) if dotted is not None else None
        else:
            level, module = 0, module_text
    if any(c.type == "wildcard_import" for c in node.children):
        names: tuple[str | None, ...] = ("*",)
        bindings: tuple[tuple[str, str], ...] = ()
    else:
        name_nodes = node.children_by_field_name("name")
        names = tuple(_dotted(n) for n in name_nodes)
        bindings = tuple((_dotted(n), _local_name(n, _dotted(n))) for n in name_nodes)
    return ImportRecord("from", module, level, names, True, _text(node), line, column, module_text, bindings)


def _string_literal(node: Node) -> str | None:
    """Value of a plain string literal; None for f-strings, bytes, concatenations or escapes."""
    if node.type != "string":
        return None
    parts = node.children
    if any(c.type not in ("string_start", "string_content", "string_end") for c in parts):
        return None
    start = next((c for c in parts if c.type == "string_start"), None)
    if start is None or not set(_text(start).rstrip("'\"")) <= _LITERAL_PREFIXES:
        return None
    value = "".join(_text(c) for c in parts if c.type == "string_content")
    return value or None


def _dynamic_call(position: Positions, node: Node, importlib_names: set[str], import_module_names: set[str]) -> ImportRecord | None:
    func = node.child_by_field_name("function")
    if func is None:
        return None
    if func.type == "identifier":
        name = _text(func)
        if name == "__import__":
            kind = "__import__"
        elif name in import_module_names:
            kind = "import_module"
        else:
            return None
    elif func.type == "attribute":
        obj, attr = func.child_by_field_name("object"), func.child_by_field_name("attribute")
        if obj is None or attr is None or obj.type != "identifier":
            return None
        if _text(obj) not in importlib_names or _text(attr) != "import_module":
            return None
        kind = "import_module"
    else:
        return None

    args = node.child_by_field_name("arguments")
    named = [c for c in args.named_children if c.type != "comment"] if args is not None else []
    positional = [c for c in named if c.type != "keyword_argument"]
    keywords = {_text(c.child_by_field_name("name")) for c in named if c.type == "keyword_argument"}
    value = _string_literal(positional[0]) if positional else None
    if kind == "import_module":
        relative_context = len(positional) > 1 or "package" in keywords
    else:
        relative_context = len(positional) > 4 or "level" in keywords
    literal = value is not None and not value.startswith(".") and not relative_context
    line, column = position(node)
    text = _text(node)
    return ImportRecord("dynamic", value if literal else None, 0, (None,), literal, text, line, column, text)


def _definitions(root: Node) -> list[Definition]:
    out: list[Definition] = []

    def unwrap(node: Node) -> Node:
        return node.child_by_field_name("definition") if node.type == "decorated_definition" else node

    for child in root.named_children:
        node = unwrap(child)
        if node is None:
            continue
        name_node = node.child_by_field_name("name")
        if name_node is None:
            continue
        name = _text(name_node)
        if node.type == "function_definition":
            out.append(Definition("function", name, node.start_point.row + 1))
        elif node.type == "class_definition":
            out.append(Definition("class", name, node.start_point.row + 1))
            body = node.child_by_field_name("body")
            for member in body.named_children if body is not None else []:
                method = unwrap(member)
                if method is not None and method.type == "function_definition":
                    method_name = method.child_by_field_name("name")
                    if method_name is not None:
                        out.append(Definition("method", f"{name}.{_text(method_name)}", method.start_point.row + 1))
    return out


def _importlib_aliases(statements: list[ImportRecord]) -> tuple[set[str], set[str]]:
    """Local names bound to `importlib` and to `importlib.import_module` by the file's own imports."""
    importlib_names, import_module_names = {"importlib"}, set()
    for record in statements:
        if record.kind == "import" and record.module == "importlib":
            importlib_names.update(local for _, local in record.bindings)
        if record.kind == "from" and record.module == "importlib" and record.level == 0:
            import_module_names.update(local for name, local in record.bindings if name == "import_module")
    return importlib_names, import_module_names


def extract(source: bytes, check: Callable[[], None] = lambda: None) -> FileFacts:
    """Parse UTF-8 source. Imports are collected from every scope, including inside error regions.

    `check` is called every few thousand nodes, so a time limit can stop work inside one large file."""
    source = normalize_newlines(source)
    tree = _PARSER.parse(source)
    root = tree.root_node
    position = Positions(source)
    statements: list[ImportRecord] = []
    calls: list[Node] = []
    stack = [root]
    visited = 0
    while stack:
        node = stack.pop()
        visited += 1
        if visited % CHECK_EVERY == 0:
            check()
        if node.type == "import_statement":
            statements.extend(_import_statement(position, node))
            continue
        if node.type in ("import_from_statement", "future_import_statement"):
            statements.append(_from_statement(position, node))
            continue
        if node.type == "call":
            calls.append(node)
        stack.extend(reversed(node.children))

    importlib_names, import_module_names = _importlib_aliases(statements)
    dynamic = [r for r in (_dynamic_call(position, c, importlib_names, import_module_names) for c in calls) if r is not None]
    imports = sorted(statements + dynamic, key=lambda r: (r.line, r.column, r.module_text))
    return FileFacts(tuple(imports), tuple(_definitions(root)), root.has_error)
