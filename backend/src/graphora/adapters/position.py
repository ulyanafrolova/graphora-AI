"""1-based line and code-point column of Tree-sitter nodes, shared by the adapters (001 data-model.md § Edge)."""

from __future__ import annotations

import re

from tree_sitter import Node

CHECK_EVERY = 4096  # syntax nodes between time-limit checks inside one file
_LONE_CR = re.compile(rb"\r(?!\n)")


def normalize_newlines(source: bytes) -> bytes:
    """A lone CR ends a line in Python and JavaScript, but Tree-sitter counts rows by LF only. Same length, so
    byte offsets and columns are unchanged."""
    return _LONE_CR.sub(b"\n", source) if b"\r" in source else source


class Positions:
    """Columns count Unicode code points. Nodes asked in source order cost O(line length) per line in total,
    so a minified file with one huge line is linear, not quadratic."""

    def __init__(self, source: bytes) -> None:
        self._source = source
        self._row = -1
        self._byte = 0  # last measured byte offset on `_row`
        self._column = 0  # code points between the start of `_row` and `_byte`

    def __call__(self, node: Node) -> tuple[int, int]:
        row, start = node.start_point.row, node.start_byte
        if row != self._row or start < self._byte:
            self._row, self._byte, self._column = row, start - node.start_point.column, 0  # Tree-sitter columns are bytes
        self._column += len(self._source[self._byte : start].decode("utf-8", errors="replace"))
        self._byte = start
        return row + 1, self._column + 1
