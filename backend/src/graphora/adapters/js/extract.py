"""Extract imports, re-exports, definitions and exports from TS/JS source with Tree-sitter. Never runs the code.

Forms and fields are defined in specs/003-ts-js-analysis/research.md § R2 and data-model.md § Definition, § Export.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from graphora.graph.model import Definition, Export

_TYPESCRIPT = Parser(Language(tree_sitter_typescript.language_typescript()))
_TSX = Parser(Language(tree_sitter_typescript.language_tsx()))
_JAVASCRIPT = Parser(Language(tree_sitter_javascript.language()))
_BOM = b"\xef\xbb\xbf"

_CLASS_TYPES = ("class_declaration", "abstract_class_declaration")
_FUNCTION_TYPES = ("function_declaration", "generator_function_declaration", "function_signature")
_FUNCTION_VALUES = ("arrow_function", "function_expression", "generator_function")
_SIMPLE_KINDS = {"interface_declaration": "interface", "type_alias_declaration": "type_alias", "enum_declaration": "enum"}


@dataclass(frozen=True)
class ImportName:
    """One imported name: the name in the target module (`default`, `*`, None for whole-module forms)."""

    symbol: str | None
    type_only: bool
    alias: str | None = None


@dataclass(frozen=True)
class ImportRecord:
    """One statement or call. `specifier` is None when it is not a literal (the edge becomes `dynamic`)."""

    edge_type: Literal["imports", "reexports"]
    form: Literal["static", "dynamic", "require"]
    specifier: str | None
    names: tuple[ImportName, ...]
    text: str
    line: int
    column: int


@dataclass(frozen=True)
class FileFacts:
    imports: tuple[ImportRecord, ...]
    definitions: tuple[Definition, ...]
    exports: tuple[Export, ...]
    has_error: bool


def _parser(path: str) -> Parser:
    if path.endswith(".tsx"):
        return _TSX
    if path.endswith((".ts", ".mts", ".cts")):
        return _TYPESCRIPT
    return _JAVASCRIPT


def _text(node: Node) -> str:
    return node.text.decode("utf-8", errors="replace")


def _position(source: bytes, node: Node) -> tuple[int, int]:
    line_start = source.rfind(b"\n", 0, node.start_byte) + 1
    column = len(source[line_start : node.start_byte].decode("utf-8", errors="replace")) + 1
    return node.start_point.row + 1, column


def _has_token(node: Node, token: str) -> bool:
    return any(c.type == token and not c.is_named for c in node.children)


def _literal(node: Node | None) -> str | None:
    """Value of a string, or of a template string without substitutions. None for anything else or escapes."""
    if node is None or node.type not in ("string", "template_string"):
        return None
    parts = node.named_children
    if any(c.type != "string_fragment" for c in parts):
        return None
    return "".join(_text(c) for c in parts)


def _record(source: bytes, node: Node, edge_type, form, specifier, names, text_node: Node | None = None) -> ImportRecord:
    line, column = _position(source, node)
    return ImportRecord(edge_type, form, specifier, tuple(names), _text(text_node or node), line, column)


def _name(node: Node) -> str:
    """An identifier, or the value of a string used as a module export name (`import { "a-b" as x }`)."""
    literal = _literal(node)
    return literal if literal is not None else _text(node)


def _import_statement(source: bytes, node: Node) -> ImportRecord | None:
    statement_type_only = _has_token(node, "type")
    require = next((c for c in node.named_children if c.type == "import_require_clause"), None)
    if require is not None:
        specifier = _literal(require.child_by_field_name("source"))
        return _record(source, node, "imports", "require", specifier, [ImportName(None, False)])
    source_node = node.child_by_field_name("source")
    if source_node is None:
        return None
    clause = next((c for c in node.named_children if c.type == "import_clause"), None)
    names: list[ImportName] = []
    for part in clause.named_children if clause is not None else []:
        if part.type == "identifier":
            names.append(ImportName("default", statement_type_only))
        elif part.type == "namespace_import":
            names.append(ImportName("*", statement_type_only))
        elif part.type == "named_imports":
            for spec in part.named_children:
                if spec.type == "import_specifier":
                    name = spec.child_by_field_name("name")
                    names.append(ImportName(_name(name), statement_type_only or _has_token(spec, "type")))
    if not names:
        names.append(ImportName(None, statement_type_only))
    return _record(source, node, "imports", "static", _literal(source_node), names)


def _reexport_statement(source: bytes, node: Node) -> ImportRecord:
    statement_type_only = _has_token(node, "type")
    names: list[ImportName] = []
    namespace = next((c for c in node.named_children if c.type == "namespace_export"), None)
    clause = next((c for c in node.named_children if c.type == "export_clause"), None)
    if namespace is not None:
        alias = next((c for c in namespace.named_children if c.type in ("identifier", "string")), None)
        names.append(ImportName("*", statement_type_only, _name(alias) if alias is not None else None))
    elif clause is not None:
        for spec in clause.named_children:
            if spec.type != "export_specifier":
                continue
            name = _name(spec.child_by_field_name("name"))
            alias_node = spec.child_by_field_name("alias")
            alias = _name(alias_node) if alias_node is not None else None
            names.append(ImportName(name, statement_type_only or _has_token(spec, "type"), alias if alias != name else None))
    else:
        names.append(ImportName("*", statement_type_only))
    return _record(source, node, "reexports", "static", _literal(node.child_by_field_name("source")), names)


def _call(source: bytes, node: Node) -> ImportRecord | None:
    func = node.child_by_field_name("function")
    args = node.child_by_field_name("arguments")
    if func is None or args is None:
        return None
    arguments = [c for c in args.named_children if c.type != "comment"]
    if func.type == "import" and arguments:
        form = "dynamic"
    elif func.type == "identifier" and _text(func) == "require" and len(arguments) == 1:
        form = "require"
    else:
        return None
    return _record(source, node, "imports", form, _literal(arguments[0]), [ImportName(None, False)])


def _imports(source: bytes, root: Node) -> list[ImportRecord]:
    records: list[ImportRecord] = []
    stack = [root]
    while stack:
        node = stack.pop()
        record = None
        if node.type == "import_statement":
            record = _import_statement(source, node)
        elif node.type == "export_statement" and node.child_by_field_name("source") is not None:
            record = _reexport_statement(source, node)
        elif node.type == "call_expression":
            record = _call(source, node)
        if record is not None:
            records.append(record)
        stack.extend(reversed(node.children))
    return sorted(records, key=lambda r: (r.line, r.column, r.text))


def _keyword_line(node: Node) -> int:
    """Line of the first token that is not a decorator: the declaring keyword."""
    first = next((c for c in node.children if c.type != "decorator"), node)
    return first.start_point.row + 1


def _bound_names(pattern: Node) -> list[str]:
    if pattern.type == "identifier":
        return [_text(pattern)]
    found: list[str] = []
    stack = [pattern]
    while stack:
        node = stack.pop()
        if node.type in ("identifier", "shorthand_property_identifier_pattern"):
            found.append(_text(node))
        elif node.type != "property_identifier":
            stack.extend(reversed(node.named_children))
    return found


class _Collector:
    """Top-level definitions plus the names each is exported under, and exported names without a definition."""

    def __init__(self) -> None:
        self.definitions: dict[str, tuple[str, int]] = {}  # qualified name -> (kind, line); first line wins
        self.exported: dict[str, set[str]] = {}
        self.exports: list[Export] = []
        self.local_exports: list[tuple[str, str, int]] = []  # (local, exported, line)

    def define(self, kind: str, name: str, line: int, exported_as: str | None = None) -> None:
        self.definitions.setdefault(name, (kind, line))
        self.exported.setdefault(name, set())
        if exported_as is not None:
            self.exported[name].add(exported_as)

    def declaration(self, node: Node, exported: bool, default: bool, export_line: int) -> None:
        """`node` is a declaration at the top level, or directly inside an `export` statement."""
        def export_name(name: str) -> str | None:
            return "default" if default else name if exported else None

        if node.type == "ambient_declaration":
            for inner in node.named_children:
                self.declaration(inner, exported, default, export_line)
            return
        name_node = node.child_by_field_name("name")
        if node.type in _CLASS_TYPES and name_node is not None:
            name = _text(name_node)
            self.define("class", name, _keyword_line(node), export_name(name))
            self._methods(name, node.child_by_field_name("body"))
        elif node.type in _FUNCTION_TYPES and name_node is not None:
            name = _text(name_node)
            self.define("function", name, _keyword_line(node), export_name(name))
        elif node.type in _SIMPLE_KINDS and name_node is not None:
            name = _text(name_node)
            self.define(_SIMPLE_KINDS[node.type], name, _keyword_line(node), export_name(name))
        elif node.type in ("lexical_declaration", "variable_declaration"):
            for declarator in node.named_children:
                if declarator.type != "variable_declarator":
                    continue
                target, value = declarator.child_by_field_name("name"), declarator.child_by_field_name("value")
                if target is None:
                    continue
                if target.type == "identifier" and value is not None and value.type in _FUNCTION_VALUES:
                    name = _text(target)
                    self.define("function", name, _keyword_line(node), export_name(name))
                elif exported:
                    self.exports.extend(Export(n, n, export_line) for n in _bound_names(target))
        elif exported and name_node is not None:
            name = _text(name_node)  # e.g. `export namespace N {}`: exported, but not a listed definition
            self.exports.append(Export(export_name(name), name, export_line))

    def _methods(self, class_name: str, body: Node | None) -> None:
        for member in body.named_children if body is not None else []:
            if member.type == "method_definition":
                name_node = member.child_by_field_name("name")
                if name_node is not None:
                    self.define("method", f"{class_name}.{_text(name_node)}", name_node.start_point.row + 1)

    def export_statement(self, node: Node) -> None:
        line = node.start_point.row + 1
        default = _has_token(node, "default")
        declaration = node.child_by_field_name("declaration")
        if declaration is not None:
            self.declaration(declaration, True, default, _keyword_line(declaration))
            return
        value = node.child_by_field_name("value")
        if value is not None:
            if value.type == "class":
                self.define("class", "default", _keyword_line(value), "default")
                self._methods("default", value.child_by_field_name("body"))
            elif value.type in _FUNCTION_VALUES:
                self.define("function", "default", _keyword_line(value), "default")
            elif value.type == "identifier":
                self.local_exports.append((_text(value), "default", line))
            else:
                self.exports.append(Export("default", None, line))
            return
        clause = next((c for c in node.named_children if c.type == "export_clause"), None)
        for spec in clause.named_children if clause is not None else []:
            if spec.type == "export_specifier":
                local = _name(spec.child_by_field_name("name"))
                alias = spec.child_by_field_name("alias")
                self.local_exports.append((local, _name(alias) if alias is not None else local, line))

    def finish(self) -> tuple[tuple[Definition, ...], tuple[Export, ...]]:
        exports = list(self.exports)
        for local, exported, line in self.local_exports:
            if local in self.definitions and "." not in local:
                self.exported[local].add(exported)
            else:
                exports.append(Export(exported, local, line))
        definitions = tuple(
            Definition(kind, name, line, tuple(sorted(self.exported[name])))
            for name, (kind, line) in sorted(self.definitions.items(), key=lambda item: (item[1][1], item[0]))
        )
        return definitions, tuple(sorted(exports, key=lambda x: (x.name, x.line)))


def _definitions(root: Node) -> tuple[tuple[Definition, ...], tuple[Export, ...]]:
    collector = _Collector()
    for node in root.named_children:
        if node.type == "export_statement":
            if node.child_by_field_name("source") is None:
                collector.export_statement(node)
        else:
            collector.declaration(node, False, False, node.start_point.row + 1)
    return collector.finish()


def extract(path: str, source: bytes) -> FileFacts | None:
    """Parse one TS/JS file, choosing the grammar by extension. None if the file is not valid UTF-8."""
    source = source.removeprefix(_BOM)
    try:
        source.decode("utf-8")
    except UnicodeDecodeError:
        return None
    root = _parser(path).parse(source).root_node
    definitions, exports = _definitions(root)
    return FileFacts(tuple(_imports(source, root)), definitions, exports, root.has_error)
