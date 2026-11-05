# Research: Graph Queries

Decisions for [plan.md](plan.md). Each item: decision, rationale, alternatives considered.

## R1 — NetworkX version

- **Decision**: add `networkx==3.7` as the only new runtime dependency. Use it for the file-level directed
  graph, strongly connected components and the condensation DAG.
- **Rationale**: the constitution names NetworkX for graph algorithms. 3.7 is the current release and supports
  Python ≥ 3.12 (it excludes only 3.14.1, which we do not use). It is pure Python, so it adds no native code
  next to tree-sitter.
- **Alternatives**: hand-written Tarjan (rejected: the constitution names NetworkX, and SCC code is easy to get
  subtly wrong); `rustworkx` (rejected: native wheel, not in the constitution).

## R2 — Reading a graph document back

- **Decision**: add `graph/load.py` with `loads(data: bytes) -> GraphDocument`. It parses JSON and builds the
  existing frozen dataclasses from `graph/model.py`, checking by hand: `schema_version == 2`, every required
  field and enum, edge `snapshot` equal to the document snapshot, every edge `source` and `target` naming an
  existing node, and the model invariants (`Edge.__post_init__`). Any failure raises `InvalidGraph(message)`.
  Edge ids are recomputed with `serialize.edge_id` and must equal the stored ids.
- **Rationale**: nothing reads a graph back today (005 stores bytes and serves them as is). Reusing the model
  keeps one definition of a node and an edge. `loads(dumps(doc)) == doc` is an easy round-trip test, and
  `dumps(loads(data)) == data` proves nothing was lost.
- **Alternatives**: validate with `jsonschema` at run time (rejected: it is a dev dependency today and pulls
  `rpds-py`, a native wheel; tests already check the analyzer's output against the schema); query raw dicts
  (rejected: every query would re-check field names, and MCP/agents would have no typed objects).
- **Ownership**: `graph/load.py` is a new module next to Ulyana's `serialize.py`, which is not changed. The PR
  asks her to review it.

## R3 — Which edges form the file graph

- **Decision**: a *link* is a pair of nodes (source file, target node) with all edges between them, sorted by
  `edge_sort_key`. `imports` and `reexports` both count; all forms (`static`, `dynamic`, `require`) count.
  Edges with confidence `unresolved` never form links (they target `unresolved:` nodes). Traversal (impact,
  cycles, key files) continues only through `file:` targets; `ext:` and `asset:` targets are end points.
- **Rationale**: matches FR-011/FR-012 and the edge cases in the spec. A dynamic import with a literal path is
  a real run-time dependency.
- **Type-only**: with `include_type_only=False` in a query, only edges with `type_only: false` are kept, and a link
  with no edges left disappears. A link is marked type-only when all its edges are type-only.

## R4 — Confidence of a chain

- **Decision**: order `resolved` > `heuristic`. The confidence of a link is the strongest among its edges
  (one resolved import line is enough to make the link a fact); the confidence of a chain or a cycle is the
  weakest among its links. Items whose confidence is `heuristic` are shown as "likely" in text output.
- **Rationale**: FR-012. No analyzer emits `heuristic` edges yet, so tests build synthetic documents.

## R5 — Impact and the choice of chain

- **Decision**: breadth-first search over reversed links from the target. Distance = number of links. For each
  dependent at distance `d`, the next hop is the dependency at distance `d-1` with the smallest node id; the
  chain is followed from there. The hop carries all edges of that link. `max_depth` stops the search; the
  answer then has `max_depth` set and `cut: true` if any node at the limit has further dependents.
- **Rationale**: FR-006, FR-015. "Smallest id at the previous level" is a fixed, explainable tie-break and
  gives the same chain whichever order NetworkX stores adjacency.
- **Alternatives**: `nx.shortest_path` per dependent (rejected: tie-break depends on insertion order and it
  repeats work per node).

## R6 — Cycles

- **Decision**: groups are the strongly connected components with two or more files, plus single files with a
  self-link. Files in a group are sorted. The example cycle is the shortest cycle through the smallest path in
  the group, found by breadth-first search inside the group with neighbours visited in id order. Groups are
  sorted by their smallest path. A group is marked `type_only` when it contains no cycle once type-only edges
  are removed (checked by recomputing components of the group on run-time links only).
- **Rationale**: FR-008, spec US2. Listing every elementary cycle can explode (`nx.simple_cycles`), so one
  example per group is given.

## R7 — Key files

- **Decision**: rank `file:` nodes by transitive dependents, then direct dependents (distinct files), then path.
  Transitive counts are computed once on the condensation DAG: in topological order, each component's
  ancestor set is the union of its predecessors' sets and the predecessors themselves, stored as Python
  integers used as bitsets. Files in one cycle group share the set and are counted without themselves.
  Files with zero dependents are not listed. Default limit 10.
- **Rationale**: a breadth-first search per file is O(N·E) — about 10⁸ steps for 5,000 files — and would miss
  SC-004. Bitsets over the condensation make it O(components · N / 64) word operations.
- **Alternatives**: PageRank or betweenness (rejected for this slice: harder to explain and to hand-check;
  hotspots in 011 can add them).

## R8 — Barrel following

- **Decision**: off by default (`follow_barrels=True` turns it on), TS/JS files only (Python files have no
  export records). For an `imports` edge `A → B` with symbol `S` (not `null`, `*` or `default` without a
  match), resolve `S` in `B`:
  1. a definition of `B` with `S` in `exported_as`, or an entry in `B.exports` named `S` → defined in `B`, stop;
  2. a `reexports` edge of `B` whose exported name (`alias` or else `symbol`) is `S` → continue in its target
     with its `symbol`;
  3. otherwise each `reexports` edge of `B` with symbol `*` and no alias (`export *`), in edge order → continue
     in its target with `S`; the first branch that finds a definition wins.
  A file already visited stops the branch. If the chain ends in a file `F ≠ B`, the dependent is also attached
  to `F`, and the evidence is the import edge plus each re-export edge in order. If nothing is found, the
  dependent stays on `B` only.
- **Rationale**: FR-010, the 003 invariant that every exported name appears once in `exported_as`, `exports`
  or a re-export edge. Only recorded exports are followed, so nothing is guessed.
- **Effect on queries**: `dependents` and `impact` gain these derived links (chains of real edges); `cycles`
  and `key_files` do not (they stay on written edges).

## R9 — Completeness note

- **Decision**: computed once per document: `unresolved_imports` = edges with confidence `unresolved`;
  `not_analyzed_files` = coverage files with status `detected_only`; `files_with_errors` = analyzed files with
  `parse_error` or `unreadable` flags. Added to dependencies, dependents, impact, neighbors and key-files
  answers (FR-014). Not added to cycles answers.
- **Rationale**: honest and cheap. Attributing unresolved imports to a target is impossible without guessing.

## R10 — Addressing a node

- **Decision**: a target string is resolved in this order: an exact node id (`file:…`, `ext:…`, `asset:…`,
  `unresolved:…`); a file path (leading `./` stripped; backslash, absolute paths and `..` segments rejected); an
  external package name if exactly one ecosystem has it (else an error listing both ids). If nothing matches,
  `NodeNotFound` reports the coverage status of that path (`detected_only`, `not_code`, a skip reason) or
  `not_in_snapshot`.
- **Rationale**: FR-003 and the first edge case in the spec.

## R11 — Answer format and CLI

- **Decision**: answers are frozen dataclasses in `graph/results.py` with a `to_dict()` and a canonical
  `dumps()` that mirrors `serialize.dumps` (sorted keys, two-space indent, UTF-8, trailing newline). Edges in
  answers use exactly the edge dict of the graph document (`serialize` field names, including `id`). The CLI
  gets one subcommand `graphora query <graph> <question> [target] [options]` with `--format text|json`
  (default `text`). `<graph>` may be `-` for standard input.
- **Rationale**: FR-015–FR-019. One dict shape for edges means MCP (006) and the verifier (008) can match
  cited edges by id against the graph.

## R12 — Golden query answers

- **Decision**: per fixture, a new hand-written file `fixtures/repos/<name>/queries.json`: a list of
  `{"question", "target", "options", "expected"}` where `expected` is a projection that can be checked by
  hand (paths, distances, chain paths with lines, cycle files, counts — no hashes). Two new fixtures cover
  what the current ones lack: `py-cycles` (three-file loop, self-import, two separate loops) and `ts-barrels`
  (two-level `export *`, renamed re-export, untraceable name, loop through type-only imports). Each new fixture
  also gets its own hand-written `expected.json`. Existing `expected.json` files are not changed.
- **Heuristic edges**: no analyzer produces them, so they are covered by unit tests on synthetic documents.
- **Rationale**: constitution VIII; the spec assumption that expected query answers are new files.

## Open item

- `/speckit-clarify` question 1 (should `impact` accept a symbol so that only importers of that symbol start
  the search?) was not answered. The plan follows the spec as written (symbol filter on `dependents` only).
  If the answer is "yes", `impact` gains `symbol=` with the same first-step filter; the design does not change.
