# Feature Specification: Graph Queries

**Feature Branch**: `004-graph-queries`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "milestone 004" — feature 004 graph queries from the team plan
(`docs/product/team-workflow.md`, round 2): the one graph query layer that the HTTP API, the MCP server and
the agents will call.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See what depends on a file and what breaks if it changes (Priority: P1)

A developer has a graph of a repository (written by `graphora analyze`) and asks "who imports
`auth/service.py`?" and "what can break if I change it?". They get the direct dependents, then every file
that depends on it transitively, each with the chain of imports that connects it and the `file:line` of
every link in that chain.

**Why this priority**: Change impact is the main question in the demo ("What breaks if I change
AuthService?") and the main tool of the Analyst agent. Every answer must point to real import lines, so the
claim verifier (feature 008) can check it later without guessing.

**Independent Test**: Run the dependents and impact queries on the fixture repositories and compare the
results with hand-checked expected answers. Every listed file must be reachable through the listed edges, and
no reachable file may be missing.

**Acceptance Scenarios**:

1. **Given** a graph where `api/routes.py` imports `auth/service.py` on line 3, **When** the developer asks
   for the direct dependents of `auth/service.py`, **Then** the answer lists `api/routes.py` with the edge
   `api/routes.py:3 → auth/service.py`, its confidence, symbol and snapshot id.
2. **Given** `c.py → b.py → a.py`, **When** the developer asks for the impact of changing `a.py`, **Then**
   the answer lists `b.py` at distance 1 and `c.py` at distance 2, and `c.py` comes with the chain
   `c.py → b.py → a.py` where every link has its `file:line`.
3. **Given** the same graph, **When** the developer limits the impact to distance 1, **Then** only `b.py` is
   listed and the answer says that the search was cut at distance 1.
4. **Given** a file that imports `a.py` only as a type (`import type`), **When** the impact of `a.py` is
   asked, **Then** that file is listed and marked as a type-only dependent, and the developer can ask to
   leave type-only links out.
5. **Given** an analyzed repository where some imports stayed `unresolved`, **When** any dependents or impact
   question is asked, **Then** the answer says how many imports in the repository could not be resolved and
   how many code files were not analyzed, so the developer knows the list may be incomplete.
6. **Given** the external package `lodash` is a node in the graph, **When** the developer asks for its
   dependents, **Then** the answer lists every file that imports `lodash`, with the import lines.

---

### User Story 2 - Find dependency cycles with evidence (Priority: P1)

A developer asks for the dependency cycles of the repository. They get every group of files that depend on
each other in a loop, and for each group one concrete cycle written as a list of import lines they can open.

**Why this priority**: Cycles are one of the four Analyst tools, a demo screen (`06-cycles.png`) and a
common reason for import errors. A cycle without the lines that form it cannot be verified or fixed.

**Independent Test**: Run the cycles query on fixtures with known cycles (and on fixtures without cycles)
and compare with hand-checked expected answers.

**Acceptance Scenarios**:

1. **Given** `a.py → b.py → c.py → a.py`, **When** cycles are asked, **Then** one group `{a.py, b.py, c.py}`
   is returned with the cycle `a.py → b.py → c.py → a.py` and the `file:line` of each of the three imports.
2. **Given** a graph without cycles, **When** cycles are asked, **Then** the answer is an empty list, not an
   error.
3. **Given** two separate loops that share no file, **When** cycles are asked, **Then** two groups are
   returned in a fixed order.
4. **Given** a file that imports itself, **When** cycles are asked, **Then** it is returned as a group of one
   file with that import line.
5. **Given** a loop that exists only through type-only imports, **When** cycles are asked, **Then** the group
   is marked as type-only, because such a loop does not fail at run time.

---

### User Story 3 - Look around a file and find the key files (Priority: P2)

A developer (or the Explorer and Analyst agents) looks at one file and asks for its neighbours: what it
imports and what imports it. They also ask which files are the most depended on in the whole repository.

**Why this priority**: Neighbours are the basic step of exploring the map and an Analyst tool. Key files
feed the "key nodes" part of the MVP and later the hotspots feature (011). Both are useful without the
impact and cycle queries, but less central to the demo.

**Independent Test**: Run the neighbours and key-files queries on the fixtures and compare with hand-checked
answers.

**Acceptance Scenarios**:

1. **Given** `b.py` imports `a.py` and `os`, and `c.py` imports `b.py`, **When** the neighbours of `b.py`
   are asked, **Then** the answer lists outgoing links to `a.py` and `os` and the incoming link from `c.py`,
   each with its edges.
2. **Given** `b.py` has an import that stayed unresolved, **When** its neighbours are asked, **Then** the
   unresolved import is listed separately with its reference text, line and reason, never as a file.
3. **Given** a repository, **When** the developer asks for the top 10 key files, **Then** the answer ranks
   project files by the number of files that depend on them transitively, then by direct dependents, then by
   path, and shows both numbers for each file.

---

### User Story 4 - See through barrel files (Priority: P3)

A developer analyzes a TypeScript project where most imports go through `index.ts` barrel files. When they
ask who uses `components/Button.tsx`, they see the files that really use `Button`, not only `index.ts`.

**Why this priority**: Feature 003 records only the edges written in code and leaves following re-export
chains to the query layer. Without it, direct dependents in barrel-heavy projects collapse into index files.
Transitive impact is already correct without it (the chain passes through the barrel), so this is a
refinement.

**Independent Test**: Run the dependents query on the `ts-app` and `ts-monorepo` fixtures with barrel files
and compare with hand-checked answers.

**Acceptance Scenarios**:

1. **Given** `app.ts` imports `{ Button }` from `components/index.ts`, which has
   `export { Button } from "./Button"`, **When** the direct dependents of `components/Button.tsx` are asked
   with barrel following on, **Then** `app.ts` is listed as a dependent through the barrel, with both edges
   (the import line and the re-export line) as evidence.
2. **Given** `export * from "./x"` chains through two barrels, **When** a file imports a name that one of
   the chained files exports, **Then** the dependent is attached to that file through the full chain.
3. **Given** a file imports a name that no file in the chain exports, **When** barrels are followed,
   **Then** the dependent stays attached to the barrel only and is not guessed onto any file.

---

### Edge Cases

- A file asked about is not in the graph: the answer says whether it is in the coverage report as
  `detected_only`, `not_code` or skipped (and why), or not in the snapshot at all. It never returns an empty
  list that looks like "no dependents".
- A file is given with `./`, a trailing slash, a backslash or `..`: the path is rejected or normalized the
  same way the graph stores paths; it never matches a file outside the graph.
- A graph document with an unsupported schema version, invalid content or edges pointing to missing nodes:
  the query stops with a clear error and gives no partial answer.
- Very large results (thousands of dependents): the developer can set a limit; the answer then holds the
  first N items in the fixed order, the total count and a "truncated" flag.
- A cycle group with many files: one example cycle is given per group, not every possible cycle.
- Several shortest chains of the same length lead to a dependent: the same chain is always chosen by a fixed
  rule.
- Edges to assets, external packages and unresolved nodes do not continue a chain; impact runs only through
  project files.
- Two import lines from the same file to the same target: both edges are kept as evidence; the file is
  listed once.
- An empty repository or a graph with no edges: every query returns an empty, valid answer.

## Requirements *(mandatory)*

### Functional Requirements

**Input**

- **FR-001**: Queries MUST run on a graph document produced by `graphora analyze` (current schema version)
  and MUST NOT read the analyzed repository, its files or the network.
- **FR-002**: A graph document MUST be validated before any query. An unsupported version or invalid
  document MUST stop with an error that names the problem; no partial answer is given.
- **FR-003**: A node MUST be addressable by its graph id, by the repository-relative path of a file, and by
  the name of an external package. Unknown targets MUST be reported as in the first edge case.

**Queries**

- **FR-004**: Direct dependencies: for a node, list the nodes it imports or re-exports, grouped by target,
  with every edge as evidence. Unresolved imports MUST be listed separately with reference, line and reason.
- **FR-005**: Direct dependents: for a node, list the files that import or re-export it, with every edge as
  evidence. It MUST be possible to filter by imported symbol name (for example only files that import
  `AuthService` from the file).
- **FR-006**: Impact: for a node, list every file that depends on it transitively, with its distance and one
  shortest chain of edges back to the node. An optional maximum distance MUST be supported and reported in
  the answer.
- **FR-007**: Neighbours: for a node, return its direct dependencies and direct dependents together.
- **FR-008**: Cycles: return every group of two or more files that depend on each other in a loop, and every
  file that imports itself, each with one example cycle given as an ordered list of edges.
- **FR-009**: Key files: rank project files by the number of transitive dependents, then by the number of
  direct dependents, then by path, and return the top N with both numbers.
- **FR-010**: Barrel following (optional per query, off by default): when a file imports a named symbol
  from a file that re-exports it, the dependent MUST also be attached to the file that defines that symbol,
  with the import edge and each re-export edge as evidence. Only exports recorded in the graph may be
  followed; a name that cannot be traced stays on the barrel.

**Honesty**

- **FR-011**: Every result item MUST carry the edges it rests on with their full provenance as stored in the
  graph (source, target, line, column, symbol, snapshot, confidence, extractor, snippet hash). A query MUST
  NOT create an edge that is not in the graph; derived links (impact chains, barrel links) MUST be given
  as lists of real edges.
- **FR-012**: Every result item MUST state its weakest confidence: an item that rests on a `heuristic` edge
  anywhere in its chain MUST be marked as likely, not as a fact. Edges with confidence `unresolved` MUST NOT
  be used to reach files.
- **FR-013**: Type-only links MUST be marked in every result that contains them, and dependents, impact and
  cycles MUST support leaving them out.
- **FR-014**: Dependents, impact, neighbours and key-files answers MUST include a completeness note: the
  number of unresolved imports and the number of code files that were detected but not analyzed in the
  snapshot.

**Determinism and size**

- **FR-015**: The same graph and the same query MUST give a byte-identical answer. Every list MUST be in a
  defined order (by path or id, then line, then column), and ties (for example between equally short chains
  or cycles) MUST be broken by a fixed rule.
- **FR-016**: List answers MUST support a limit. A limited answer MUST hold the first N items in the defined
  order, the total count and a flag that it was truncated.
- **FR-017**: Every answer MUST state the snapshot id of the graph it was computed on and echo the query and
  its options.

**Access**

- **FR-018**: All queries MUST be read-only and MUST live in the one graph query layer; later features (HTTP
  API, MCP server, agent tools, verifier) MUST reuse them rather than reimplement them.
- **FR-019**: The developer MUST be able to run each query from the command line on a graph file and get
  the answer both as readable text and as machine-readable output following a documented format.

### Key Entities

- **Graph document**: the input; the serialized graph of one snapshot (nodes, edges with provenance,
  coverage report).
- **Query**: a question type (dependencies, dependents, impact, neighbours, cycles, key files) with its
  target node and options (symbol filter, maximum distance, type-only filter, barrel following, limit).
- **Evidence chain**: an ordered list of real graph edges that connects two nodes; its confidence is the
  weakest confidence among its edges.
- **Result item**: one file or package in an answer, with its numbers (distance, counts) and its evidence.
- **Cycle group**: a set of files that depend on each other in a loop, with one example cycle.
- **Completeness note**: counts of unresolved imports and not-analyzed code files that may hide links.
- **Answer**: snapshot id, echoed query, ordered items, total count, truncated flag and completeness note.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On every fixture repository, 100% of hand-checked expected dependents, impact sets, cycle
  groups and key-file rankings are returned, with no extra items.
- **SC-002**: 100% of edges cited in any answer exist in the input graph with identical provenance, and every
  impact chain and cycle is a connected walk of those edges.
- **SC-003**: Running every query twice on every fixture gives byte-identical answers.
- **SC-004**: On a graph of a repository at the default ingest limits (5,000 files), each query answers in
  under 1 second after the graph is loaded, and loading takes under 2 seconds, on a typical developer laptop.
- **SC-005**: 0 answers in the test suite present a link through a `heuristic` edge as a fact, or reach a
  file through an `unresolved` edge.
- **SC-006**: A developer can answer "what breaks if I change file X?" from the command line with one
  command and open every cited `file:line` from the answer.

## Assumptions

- This is feature 004 from the team plan, owned by Anna. Storage and the HTTP API are feature 005 (FR-019
  there says graph queries belong to 004 and are exposed over HTTP later); the MCP server is 006; the claim
  verifier and agent tools are 008. This slice adds no HTTP or MCP surface.
- Queries work on files and external packages. Symbol-level questions are limited to filtering edges by the
  imported symbol name; call graphs and symbol search are out of scope.
- The input is the current graph schema (version 2). This slice does not change the schema or the fixtures'
  `expected.json`; expected query answers for the fixtures are new hand-written files next to them.
- `heuristic` edges do not exist yet (they come with the frontend ↔ backend bridge, feature 012), but the
  queries handle them now so later features need no change.
- Key-file ranking uses transitive and direct dependent counts because they are deterministic and easy to
  explain; other centrality measures and hotspots (feature 011) are out of scope.
- Cycle-breaking advice, architecture rules, "tests to run" and graph diffs are later features that will
  build on these queries.
- Readable text output is for people; agents and later features use the machine-readable output.
