"""Definition and mention claims, checked against the stored file text (specs/011-claim-verifier research § R6).
Text comes only from the store, never from files on disk."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Protocol

from graphora.graph.model import FileNode
from graphora.graph.queries import GraphIndex
from graphora.verify.claims import Check, Claim, Line, Verdict

if TYPE_CHECKING:
    from graphora.store import FileText, Store


class TextSource(Protocol):
    def get(self, path: str) -> FileText | None: ...


class _StoreText:
    def __init__(self, store: Store, repository: str, snapshot: str) -> None:
        self._store, self._repository, self._snapshot = store, repository, snapshot

    def get(self, path: str) -> FileText | None:
        return self._store.get_file(self._repository, self._snapshot, path)


class Cached:
    """Reads each file once; one per `verify` call."""

    def __init__(self, source: TextSource) -> None:
        self._source = source
        self._files: dict[str, FileText | None] = {}

    def get(self, path: str) -> FileText | None:
        if path not in self._files:
            self._files[path] = self._source.get(path)
        return self._files[path]


def store_text(store: Store, repository: str, snapshot: str) -> TextSource:
    return _StoreText(store, repository, snapshot)


def has_name(line: str, symbol: str) -> bool:
    """The last `.` part of the symbol as a whole name: not next to a letter, digit, `_` or `$`."""
    name = symbol.rsplit(".", 1)[-1]
    return re.search(rf"(?<![\w$]){re.escape(name)}(?![\w$])", line) is not None


def _nearest(lines: tuple[str, ...], line: int, symbol: str) -> int | None:
    found = [n for n, text in enumerate(lines, start=1) if has_name(text, symbol)]
    return min(found, key=lambda n: (abs(n - line), n)) if found else None


def check_text(ix: GraphIndex, claim: Claim, text: TextSource | None, checks: list[Check]) -> Verdict:
    path, line, symbol = claim.path, claim.line, claim.symbol

    def rejected(name: str, detail: str, reason, hint: str | None = None) -> Verdict:
        checks.append(Check(name, False, detail))
        return Verdict("rejected", tuple(checks), reason, hint)

    if path not in ix.coverage:
        return rejected("file", f"{path} is not in snapshot {ix.doc.snapshot}", "file_not_in_snapshot")
    checks.append(Check("file", True, path))
    found = None if text is None else text.get(path)
    if found is None or not found.has_text:
        return rejected("text", f"no stored text for {path}", "text_unavailable")
    checks.append(Check("text", True, f"{found.line_count} lines"))
    if line > found.line_count:
        return rejected("range", f"line {line} is past the end", "line_out_of_range", f"file has {found.line_count} lines")
    checks.append(Check("range", True, f"line {line}"))

    if claim.kind == "definition":
        node = ix.nodes.get(f"file:{path}")
        defined = sorted(
            d.line for d in (node.definitions if isinstance(node, FileNode) else ()) if symbol in (d.name, d.name.rsplit(".", 1)[-1])
        )
        if not defined:
            return rejected("definition", f"{symbol} is not defined in {path}", "definition_not_in_graph")
        if line not in defined:
            hint = f"defined on line {defined[0]}"
            return rejected("definition", f"{symbol} is not defined on line {line}", "symbol_not_on_line", hint)
        checks.append(Check("definition", True, f"{symbol} on line {line}"))

    stored = found.lines[line - 1]
    if not has_name(stored, symbol):
        nearest = None if claim.kind == "definition" else _nearest(found.lines, line, symbol)
        hint = None if nearest is None else f"found on line {nearest}"
        return rejected("symbol", f"{symbol} is not on line {line}", "symbol_not_on_line", hint)
    checks.append(Check("symbol", True, symbol))
    return Verdict("verified", tuple(checks), proof=(Line(path, line, stored),))
