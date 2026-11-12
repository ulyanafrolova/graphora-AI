"""C# extraction (specs/007-csharp-analysis research.md § R1, data-model.md § Internal entities)."""

import tree_sitter_c_sharp
from tree_sitter import Language, Parser


def test_pinned_grammar_loads_with_pinned_tree_sitter():
    language = Language(tree_sitter_c_sharp.language())
    assert language.abi_version >= 14
    tree = Parser(language).parse(b"namespace A; class B {}")
    assert not tree.root_node.has_error
