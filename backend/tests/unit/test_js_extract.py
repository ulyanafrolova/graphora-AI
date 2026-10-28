"""TS/JS extraction (specs/003-ts-js-analysis research.md § R2, data-model.md § Definition and § Export)."""

import pytest

from graphora.adapters.js.extract import ImportName, extract
from graphora.graph.model import Definition, Export


def _facts(source, path="a.ts"):
    facts = extract(path, source.encode("utf-8"))
    assert facts is not None
    return facts


def _one(source, path="a.ts"):
    records = _facts(source, path).imports
    assert len(records) == 1, records
    return records[0]


def _names(record):
    return [(n.symbol, n.type_only, n.alias) for n in record.names]


# --- import forms (research R2) ---------------------------------------------------------------


@pytest.mark.parametrize(
    "source, form, specifier, names",
    [
        ('import x from "m";', "static", "m", [("default", False, None)]),
        ('import { a, b as c } from "m";', "static", "m", [("a", False, None), ("b", False, None)]),
        ('import * as ns from "m";', "static", "m", [("*", False, None)]),
        ('import "./side";', "static", "./side", [(None, False, None)]),
        ('import type { T } from "./t";', "static", "./t", [("T", True, None)]),
        ('import { type A, B } from "./t";', "static", "./t", [("A", True, None), ("B", False, None)]),
        ('import x, { a } from "m";', "static", "m", [("default", False, None), ("a", False, None)]),
        ('import fs = require("fs");', "require", "fs", [(None, False, None)]),
        ('const c = require("lodash");', "require", "lodash", [(None, False, None)]),
        ('const p = import("./p");', "dynamic", "./p", [(None, False, None)]),
    ],
)
def test_import_forms(source, form, specifier, names):
    record = _one(source)
    assert record.edge_type == "imports"
    assert (record.form, record.specifier, _names(record)) == (form, specifier, names)


def test_snippet_text_is_statement_or_call():
    assert _one('import { a,\n  b } from "m";').text == 'import { a,\n  b } from "m";'
    assert _one('const c = require("x");').text == 'require("x")'
    assert _one('foo(import("./p"));').text == 'import("./p")'


@pytest.mark.parametrize(
    "source",
    ["require(name);", 'require("./a" + b);', "require(`./${a}`);", "import(`./p/${n}`);", 'require("a\\x41");'],
)
def test_non_literal_specifiers_are_dynamic(source):
    record = _one(source)
    assert record.specifier is None
    assert record.text == source.rstrip(";")


def test_template_without_substitution_is_literal():
    assert _one("require(`./a`);").specifier == "./a"


def test_require_shapes_that_do_not_count():
    assert _facts('require("a", "b"); obj.require("x"); require();').imports == ()


def test_calls_in_nested_scopes():
    source = 'function f() {\n  if (x) {\n    const a = require("a");\n    return import("./b");\n  }\n}\n'
    records = _facts(source).imports
    assert [(r.specifier, r.line, r.column) for r in records] == [("a", 3, 15), ("./b", 4, 12)]


def test_column_counts_code_points():
    record = _facts('const s = "ü"; const a = require("a");').imports[0]
    assert (record.line, record.column) == (1, 26)


# --- definitions (data-model.md § Definition) --------------------------------------------------


def _defs(source, path="a.ts"):
    return [(d.kind, d.name, d.line, d.exported_as) for d in _facts(source, path).definitions]


def test_definition_kinds():
    source = (
        "class C {}\n"
        "abstract class A {}\n"
        "function f() {}\n"
        "function* g() {}\n"
        "async function h() {}\n"
        "const k = () => 1, v = 5;\n"
        "let j = function () {};\n"
        "interface I {}\n"
        "type T = 1;\n"
        "enum E { A }\n"
        "const enum CE { B }\n"
        "declare function d(): void;\n"
    )
    assert _defs(source) == [
        ("class", "C", 1, ()),
        ("class", "A", 2, ()),
        ("function", "f", 3, ()),
        ("function", "g", 4, ()),
        ("function", "h", 5, ()),
        ("function", "k", 6, ()),
        ("function", "j", 7, ()),
        ("interface", "I", 8, ()),
        ("type_alias", "T", 9, ()),
        ("enum", "E", 10, ()),
        ("enum", "CE", 11, ()),
        ("function", "d", 12, ()),
    ]


def test_methods_and_skipped_members():
    source = (
        "abstract class C {\n"
        "  x = 1;\n"
        "  m() {}\n"
        "  get g() { return 1 }\n"
        "  set g(v) {}\n"
        "  abstract z(): void;\n"
        "}\n"
    )
    assert _defs(source) == [("class", "C", 1, ()), ("method", "C.m", 3, ()), ("method", "C.g", 4, ())]


def test_not_listed():
    source = "function outer() { function inner() {} }\nnamespace N { export const q = 1 }\nif (x) { function y() {} }\n"
    assert _defs(source) == [("function", "outer", 1, ())]


def test_overloads_collapse_to_first_line():
    source = "function f(a: string): void;\nfunction f(a: number): void;\nfunction f(a: any) {}\n"
    assert _defs(source) == [("function", "f", 1, ())]


def test_line_ignores_decorator():
    assert _defs("@dec()\nclass D {}\n") == [("class", "D", 2, ())]
    assert _defs("@dec()\nexport class D {}\n") == [("class", "D", 2, ("D",))]


def test_export_on_declaration():
    source = "export class C {}\nclass P {}\nexport const f = () => 1;\nexport const x = 1, y = 2;\nexport interface I {}\n"
    facts = _facts(source)
    assert [(d.name, d.exported_as) for d in facts.definitions] == [("C", ("C",)), ("P", ()), ("f", ("f",)), ("I", ("I",))]
    assert facts.exports == (Export("x", "x", 4), Export("y", "y", 4))


def test_javascript_definitions_have_export_info():
    assert _defs("export function f() {}\nclass C { m() {} }\n", "a.js") == [
        ("function", "f", 1, ("f",)),
        ("class", "C", 2, ()),
        ("method", "C.m", 2, ()),
    ]


# --- grammar choice and errors -----------------------------------------------------------------


@pytest.mark.parametrize("path", ["a.tsx", "a.jsx", "a.js"])
def test_jsx_parses(path):
    assert not _facts("const el = <div>{x}</div>;", path).has_error


def test_jsx_in_ts_is_parse_error():
    assert _facts("const el = <div>{x}</div>;", "a.ts").has_error


def test_ts_angle_cast_in_ts():
    assert not _facts("const n = <number>x;", "a.ts").has_error


def test_syntax_error_keeps_intact_imports():
    facts = _facts('import a from "./a";\nfunction (\nimport b from "./b";\n')
    assert facts.has_error
    assert "./a" in [r.specifier for r in facts.imports]


def test_bom_stripped_and_invalid_utf8():
    facts = extract("a.ts", b'\xef\xbb\xbfimport a from "./a";')
    assert facts.imports[0].column == 1
    assert extract("a.ts", b"import a from '\xff';") is None


def test_records_sorted_by_position():
    records = _facts('const b = require("b");\nimport a from "./a";\n').imports
    assert [r.line for r in records] == [1, 2]


def test_import_name_type():
    assert ImportName("a", False) == ImportName("a", False, None)
    assert Definition("class", "C", 1, ()).exported_as == ()


# --- re-exports and export lists (US2) ---------------------------------------------------------


@pytest.mark.parametrize(
    "source, specifier, names",
    [
        ('export * from "./all";', "./all", [("*", False, None)]),
        ('export * as ns from "./all";', "./all", [("*", False, "ns")]),
        ('export { a, b as c } from "./m";', "./m", [("a", False, None), ("b", False, "c")]),
        ('export { a as a } from "./m";', "./m", [("a", False, None)]),
        ('export type { T } from "./t";', "./t", [("T", True, None)]),
        ('export { type T, v } from "./t";', "./t", [("T", True, None), ("v", False, None)]),
        ('export { a as b, a as c } from "./x";', "./x", [("a", False, "b"), ("a", False, "c")]),
    ],
)
def test_reexport_forms(source, specifier, names):
    record = _one(source)
    assert (record.edge_type, record.form, record.specifier, _names(record)) == ("reexports", "static", specifier, names)


def test_reexports_do_not_touch_definitions():
    facts = _facts('export { f } from "./m";\nfunction f() {}\n')
    assert [(d.name, d.exported_as) for d in facts.definitions] == [("f", ())]
    assert facts.exports == ()


def test_local_export_lists():
    facts = _facts("function f() {}\nconst v = 1;\nexport { f, f as g, v as w };\n")
    assert [(d.name, d.exported_as) for d in facts.definitions] == [("f", ("f", "g"))]
    assert facts.exports == (Export("w", "v", 3),)


@pytest.mark.parametrize(
    "source, definitions, exports",
    [
        ("export default class C {}", [("class", "C", 1, ("default",))], ()),
        ("export default class {}", [("class", "default", 1, ("default",))], ()),
        ("export default function () {}", [("function", "default", 1, ("default",))], ()),
        ("export default () => 1;", [("function", "default", 1, ("default",))], ()),
        ("const router = 1;\nexport default router;", [], (Export("default", "router", 2),)),
        ("function f() {}\nexport default f;", [("function", "f", 1, ("default",))], ()),
        ("export default { a: 1 };", [], (Export("default", None, 1),)),
    ],
)
def test_export_default(source, definitions, exports):
    facts = _facts(source)
    assert [(d.kind, d.name, d.line, d.exported_as) for d in facts.definitions] == definitions
    assert facts.exports == exports


def test_import_then_export():
    facts = _facts('import { a } from "./m";\nexport { a as b };\n')
    assert facts.exports == (Export("b", "a", 2),)
    assert [r.edge_type for r in facts.imports] == ["imports"]


def test_every_exported_name_once():
    source = (
        'export * from "./all";\n'
        'export { r as r2 } from "./r";\n'
        "export class C {}\n"
        "function f() {}\n"
        "export { f as g };\n"
        "export default f;\n"
        "export const x = 1;\n"
        'import { a } from "./m";\n'
        "export { a };\n"
    )
    facts = _facts(source)
    names = [n for d in facts.definitions for n in d.exported_as]
    names += [x.name for x in facts.exports]
    names += [n.alias or n.symbol for r in facts.imports if r.edge_type == "reexports" for n in r.names if n.symbol != "*" or n.alias]
    assert sorted(names) == ["C", "a", "default", "g", "r2", "x"]
