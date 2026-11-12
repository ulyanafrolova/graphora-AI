"""Project-level view of a graph document, computed when asked (specs/009-csharp-solutions-project-views research
§ R4). Nothing here is stored: every project link is backed by the file-level edges it was built from.

Part of the one query layer (constitution VII): `queries.py` calls it; the CLI, API and MCP never do directly.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import networkx as nx

from graphora.graph.model import Edge, FileNode, ProjectNode
from graphora.graph.results import LinkConfidence, strongest
from graphora.graph.serialize import edge_sort_key

_CODE_EDGES = frozenset({"imports", "type_reference"})
_DECLARED_EDGES = frozenset({"project_reference", "package_reference"})


@dataclass(frozen=True)
class ProjectLink:
    """`source` is a `project:` id; `target` a `project:` or `ext:nuget:` id."""

    source: str
    target: str
    evidence: tuple[Edge, ...]  # file-level edges between files of the two projects (or to the package)
    declared: tuple[Edge, ...]  # project_reference / package_reference edges for the pair

    @property
    def declared_only(self) -> bool:
        return not self.evidence

    @property
    def confidence(self) -> LinkConfidence:
        return strongest(e.confidence for e in (self.evidence or self.declared))


class ProjectView:
    """Built once per GraphIndex by `project_view()`; read-only afterwards."""

    def __init__(self, nodes: dict, edges: tuple[Edge, ...]) -> None:
        self.projects: tuple[str, ...] = tuple(sorted(i for i, n in nodes.items() if isinstance(n, ProjectNode)))
        self.file_project: dict[str, str | None] = {
            i: n.project for i, n in sorted(nodes.items()) if isinstance(n, FileNode) and n.language == "csharp"
        }
        evidence: dict[tuple[str, str], list[Edge]] = defaultdict(list)
        declared: dict[tuple[str, str], list[Edge]] = defaultdict(list)
        for e in edges:
            if e.confidence == "unresolved":
                continue
            if e.type in _CODE_EDGES:
                source = self.file_project.get(e.source)
                if source is None:
                    continue
                if e.target.startswith("file:"):
                    target = self.file_project.get(e.target)
                    if target is not None and target != source:
                        evidence[(source, target)].append(e)
                elif e.target.startswith("ext:nuget:"):
                    evidence[(source, e.target)].append(e)
            elif e.type in _DECLARED_EDGES:
                declared[(e.source, e.target)].append(e)
        self.links: dict[tuple[str, str], ProjectLink] = {
            pair: ProjectLink(
                pair[0],
                pair[1],
                tuple(sorted(evidence.get(pair, ()), key=edge_sort_key)),
                tuple(sorted(declared.get(pair, ()), key=edge_sort_key)),
            )
            for pair in sorted(set(evidence) | set(declared))
        }
        # every link (dependencies, dependents) and code links between projects only (impact, cycles)
        self.graph = _digraph(self.projects, self.links)
        self.code_graph = _digraph(
            self.projects,
            {p: link for p, link in self.links.items() if not link.declared_only and p[1].startswith("project:")},
        )

    def files_of(self, project: str | None) -> tuple[str, ...]:
        return tuple(f for f, p in self.file_project.items() if p == project)


def _digraph(projects: tuple[str, ...], links: dict[tuple[str, str], ProjectLink]) -> nx.DiGraph:
    """Nodes and links in sorted order, so NetworkX iteration order is fixed (004 research R3)."""
    g = nx.DiGraph()
    g.add_nodes_from(projects)
    for pair in sorted(links):
        g.add_edge(*pair, link=links[pair])
    return g
