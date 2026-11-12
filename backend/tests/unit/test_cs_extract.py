"""C# extraction (specs/007-csharp-analysis research.md § R1, data-model.md § Internal entities)."""

import pytest
import tree_sitter_c_sharp
from tree_sitter import Language, Parser

from graphora.adapters.csharp.extract import UsingRecord, extract
from graphora.graph.model import Definition


def test_pinned_grammar_loads_with_pinned_tree_sitter():
    language = Language(tree_sitter_c_sharp.language())
    assert language.abi_version >= 14
    tree = Parser(language).parse(b"namespace A; class B {}")
    assert not tree.root_node.has_error


def _facts(source: str):
    facts = extract(source.encode("utf-8"))
    assert facts is not None
    return facts


def _using(source: str) -> UsingRecord:
    usings = _facts(source).usings
    assert len(usings) == 1, usings
    return usings[0]


# --- using directives ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, form, global_using, alias, target, rooted",
    [
        ("using A.B;", "using", False, None, "A.B", False),
        ("using A;", "using", False, None, "A", False),
        ("using static A.B.C;", "using_static", False, None, "A.B.C", False),
        ("using J = A.B.C;", "using_alias", False, "J", "A.B.C", False),
        ("global using A.B;", "using", True, None, "A.B", False),
        ("global using static System.Math;", "using_static", True, None, "System.Math", False),
        ("global using J = A.B;", "using_alias", True, "J", "A.B", False),
        ("using global::System.IO;", "using", False, None, "System.IO", True),
        ("using L = System.Collections.Generic.List<int>;", "using_alias", False, "L", "System.Collections.Generic.List", False),
        ("using D = System.Collections.Generic.Dictionary<string, A.B>;", "using_alias", False, "D", "System.Collections.Generic.Dictionary", False),
        ("using  A . B ;", "using", False, None, "A.B", False),
        ("using P = (int, int);", "using_alias", False, "P", None, False),
        ("using N = int;", "using_alias", False, "N", None, False),
        ("using Arr = int[];", "using_alias", False, "Arr", None, False),
    ],
)
def test_using_forms(source, form, global_using, alias, target, rooted):
    u = _using(source)
    assert (u.form, u.global_using, u.alias, u.target, u.rooted) == (form, global_using, alias, target, rooted)
    assert (u.line, u.column, u.namespace) == (1, 1, "")
    assert u.text == source


def test_using_inside_namespace_block_records_the_namespace():
    u = _using("namespace Co.App {\n  using Services;\n}")
    assert (u.target, u.namespace, u.line, u.column) == ("Services", "Co.App", 2, 3)


def test_using_inside_nested_namespace_blocks():
    u = _using("namespace A { namespace B.C { using X; } }")
    assert u.namespace == "A.B.C"


def test_usings_before_a_file_scoped_namespace_are_file_level():
    u = _using("using X.Y;\nnamespace A.B;\nclass C {}")
    assert u.namespace == ""


def test_usings_inside_preprocessor_blocks_are_kept():
    usings = _facts("#if DEBUG\nusing A;\n#else\nusing B;\n#endif\nclass C {}").usings
    assert [(u.target, u.line) for u in usings] == [("A", 2), ("B", 4)]


def test_column_counts_code_points():
    u = _using("/* é */\tusing A;")
    assert (u.line, u.column) == (1, 9)


def test_using_statement_in_a_method_is_not_a_directive():
    facts = _facts("class C { void M() { using (var s = Open()) {} using var t = Open(); } }")
    assert facts.usings == ()


# --- namespaces and definitions -------------------------------------------------------------------------------


def test_every_kind_with_fully_qualified_names():
    source = """namespace App;
public class Program {
    static void Main() {}
    private class Inner { void Run() {} }
}
struct S {}
record R(int A);
record struct RS(int B);
interface I { void Do(); }
enum E { A }
delegate void D(int x);
"""
    facts = _facts(source)
    assert facts.definitions == (
        Definition("class", "App.Program", 2),
        Definition("method", "App.Program.Main", 3),
        Definition("class", "App.Program.Inner", 4),
        Definition("method", "App.Program.Inner.Run", 4),
        Definition("struct", "App.S", 6),
        Definition("record", "App.R", 7),
        Definition("record", "App.RS", 8),
        Definition("interface", "App.I", 9),
        Definition("method", "App.I.Do", 9),
        Definition("enum", "App.E", 10),
        Definition("delegate", "App.D", 11),
    )
    assert facts.namespaces == ("App",)
    assert {t.name: t.namespace for t in facts.types} == {
        "App.Program": "App",
        "App.Program.Inner": "App",
        "App.S": "App",
        "App.R": "App",
        "App.RS": "App",
        "App.I": "App",
        "App.E": "App",
        "App.D": "App",
    }


def test_block_and_nested_namespaces_and_global_namespace():
    facts = _facts("namespace A { class X {} namespace B.C { class Y {} } }\nnamespace D { class Z {} }\nclass G {}")
    assert facts.namespaces == ("A", "A.B.C", "D")
    assert [(t.name, t.namespace) for t in facts.types] == [("A.X", "A"), ("A.B.C.Y", "A.B.C"), ("D.Z", "D"), ("G", "")]


def test_generic_type_name_drops_parameters():
    facts = _facts("namespace A { class Box<T> { void Put<U>(U u) {} } }")
    assert [d.name for d in facts.definitions] == ["A.Box", "A.Box.Put"]


def test_partial_modifier():
    facts = _facts("namespace A { public partial class P {} class Q {} }")
    assert [(t.name, t.partial) for t in facts.types] == [("A.P", True), ("A.Q", False)]


def test_local_functions_are_not_definitions():
    facts = _facts("class C { void M() { int Local() => 1; } }")
    assert [d.name for d in facts.definitions] == ["C", "C.M"]


def test_types_in_preprocessor_branches_are_kept():
    facts = _facts("namespace A {\n#if NET8_0\nclass X {}\n#else\nclass Y {}\n#endif\n}")
    assert [t.name for t in facts.types] == ["A.X", "A.Y"]


def test_syntax_error_keeps_readable_parts():
    facts = _facts("using A;\nnamespace N { class Ok {} class Broken { void x( } }")
    assert facts.has_error
    assert [u.target for u in facts.usings] == ["A"]
    assert "N.Ok" in [t.name for t in facts.types]


def test_bom_and_invalid_utf8():
    assert extract(b"\xef\xbb\xbfusing A;").usings[0].target == "A"
    assert extract(b"class \xff {}") is None


# --- type references (specs/008-csharp-type-references research.md § R1) -------------------------------------


def _refs(source: str, kind: str | None = None):
    return [(r.name, r.kind, r.line) for r in _facts(source).type_refs if kind is None or r.kind == kind]


POSITIONS = """namespace A;
[Serializable, My.Check(1)]
class C<T> : Base<T>, IThing where T : IOther {
  Field f; List<Order> xs; event Handler E; Dto? n; Item[] arr; (Left, Right) pair;
  Ret M(Param p, out Res r) {
    var v = new Made(); Local l = null; T t = default;
    var q = typeof(Ty); var c = (Cast)o; var a = o as As;
    if (o is Pat pp) {}
    try {} catch (Exc e) {}
    App.Models.User u = null; global::G.H g; Gen<Arg1, Dictionary<string, Arg2>> gg;
  }
  Prop P { get; set; }
}
"""


def test_every_type_position():
    names = [n for n, k, _ in _refs(POSITIONS) if k != "qualifier"]
    assert names == [
        "Serializable", "My.Check", "Base", "IThing", "IOther",
        "Field", "List", "Order", "Handler", "Dto", "Item", "Left", "Right",
        "Ret", "Param", "Res", "Made", "Local",
        "Ty", "Cast", "As", "Pat", "Exc",
        "App.Models.User", "G.H", "Gen", "Arg1", "Dictionary", "Arg2",
        "Prop",
    ]


def test_attribute_kind_and_rooted_name():
    facts = _facts(POSITIONS)
    kinds = {r.name: r.kind for r in facts.type_refs}
    assert kinds["Serializable"] == kinds["My.Check"] == "attribute"
    rooted = {r.name: r.rooted for r in facts.type_refs}
    assert rooted["G.H"] and not rooted["App.Models.User"]


def test_type_parameters_var_and_keywords_are_not_references():
    names = [n for n, _, _ in _refs("class C<T> { void M<U>(T t, U u, int i, string s) { var x = 1; dynamic d = null; } }")]
    assert names == []


def test_namespace_and_position_of_references():
    facts = _facts("namespace A.B {\n  class C {\n    Mailer m;\n  }\n}\n")
    (ref,) = facts.type_refs
    assert (ref.name, ref.namespace, ref.line, ref.column, ref.text) == ("Mailer", "A.B", 3, 5, "Mailer m;")


def test_file_scoped_namespace_applies_to_references():
    (ref,) = _facts("using X;\nnamespace A.B;\nclass C { Mailer m; }\n").type_refs
    assert ref.namespace == "A.B"


def test_static_member_qualifiers_but_not_variables():
    source = """class C {
  Order order;
  void M(Param p) {
    Static.Call();
    App.Util.Strings.Upper("x");
    order.Total();
    p.Run();
    var local = 1; local.ToString();
    this.Go();
    GetIt().Then();
  }
}"""
    assert _refs(source, "qualifier") == [
        ("Static", "qualifier", 4),
        ("App", "qualifier", 5),
        ("App.Util", "qualifier", 5),
        ("App.Util.Strings", "qualifier", 5),
    ]


def test_nameof_argument_is_a_qualifier():
    assert _refs("class C { string s = nameof(Mailer); string t = nameof(Clock.Now); }", "qualifier") == [
        ("Mailer", "qualifier", 1),
        ("Clock", "qualifier", 1),
    ]


def test_generic_method_type_arguments():
    names = [n for n, _, _ in _refs("class C { void M() { Resolve<Service>(); } }") if _ != "qualifier"]
    assert "Service" in names


def test_references_in_preprocessor_branches_and_broken_code():
    names = [n for n, _, _ in _refs("class C {\n#if DEBUG\n  Debugger d;\n#else\n  Release r;\n#endif\n  void M( { Kept k; }\n}")]
    assert {"Debugger", "Release"} <= set(names)


def test_using_directives_and_namespace_names_are_not_references():
    assert _facts("using A.B;\nusing X = C.D;\nnamespace E.F { }").type_refs == ()
