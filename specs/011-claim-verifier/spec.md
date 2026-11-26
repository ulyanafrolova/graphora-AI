1# Feature Specification: Claim Verifier and Agent Tools

**Feature Branch**: `011-claim-verifier`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "011 claim verifier and agent tools" — feature 011 from the team plan
(`docs/product/team-workflow.md`, round 4, issue #29). Feature 012 agents (issue #28) is built on top of it.

## Clarifications

### Session 2026-11-26

- Q: Where does the verifier take file text from? → A: Only from the store (005), like the MCP `read_lines`
  tool; no reading from the analyzed folder.
- Q: When a dependency claim names the imported name, is the name checked? → A: Yes. The cited line must hold
  an edge with that name, matched by the same rule as the `symbol` filter of dependents; otherwise `rejected`
  with "name not imported" and a hint listing the imported names. Without a name only file → target is checked.
- Q: How far are agent tool answers trimmed? → A: At most 20 items, 60 file lines per call and about 4,000
  characters of text per answer, with a note on how to get the rest.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A dependency claim is checked against the graph (Priority: P1)

The Reviewer agent (feature 012) gets a claim from the Analyst: "`api/routes.py` depends on
`auth/service.py`, see `api/routes.py:3`". It hands the claim to the verifier. The verifier, which is plain
code without any model, looks in the snapshot's graph, finds the import edge from `api/routes.py` to
`auth/service.py` on line 3 and returns the verdict "verified" with that edge as proof. A claim "`frontend/
login.ts` depends on `auth/service.py`" with no such edge in the graph comes back "rejected: no edge", so the
Reviewer can send it back or downgrade it to a hypothesis.

**Why this priority**: This is the product's core promise: every fact in an agent answer is checked by code
against the graph. Dependency claims are the most common claims in architecture answers ("what breaks if I
change X") and the graph already holds every edge with `file:line`, so this is the smallest useful verifier.

**Independent Test**: For a fixture graph, phrase every edge of its `expected.json` as a dependency claim and
check that each one is verified; change the target, the source or the line of each claim and check that each
changed claim is rejected with the right reason.

**Acceptance Scenarios**:

1. **Given** a graph where `api/routes.py` imports `auth/service.py` on line 3 (resolved), **When** the claim
   "`api/routes.py` depends on `auth/service.py` at line 3" is verified, **Then** the verdict is `verified` and
   cites that edge with its confidence, extractor and snapshot id.
2. **Given** the same graph, **When** the claim cites line 5 instead of line 3, **Then** the verdict is
   `rejected` with the reason "edge not on the cited line" and names line 3 as the line where the edge is.
3. **Given** a graph with no edge between `frontend/login.ts` and `auth/service.py`, **When** a claim says one
   depends on the other, **Then** the verdict is `rejected` with the reason "no edge in the graph".
4. **Given** a link that exists only as a heuristic edge (for example a C# namespace spread), **When** a claim
   relies on it, **Then** the verdict is `heuristic`: supported, but never to be stated as a fact.
5. **Given** an import whose target the analyzer could not resolve, **When** a claim names a target for it,
   **Then** the verdict is `rejected` with the reason "import is unresolved": an unresolved import never proves
   any target.
6. **Given** a chain claim "`a.py` → `b.py` → `c.py`" (a transitive dependency or a cycle), **When** it is
   verified, **Then** each step is checked as a dependency claim, and the chain is `verified` only if every
   step is, `heuristic` if the weakest step is heuristic, and `rejected` if any step is rejected, naming the
   step.
7. **Given** a claim whose citation names another snapshot than the one being checked, **When** it is
   verified, **Then** the verdict is `rejected` with the reason "snapshot mismatch".
8. **Given** `auth/service.py` has 3 direct dependents, all resolved, **When** the claim "`auth/service.py`
   has 3 direct dependents" is verified, **Then** the verdict is `verified`; the claim "4 direct dependents"
   is `rejected` with the reason "count mismatch" and the actual count 3.
9. **Given** `c.py` is in the impact of `a.py` at distance 2, **When** the claim "`c.py` is affected by a
   change to `a.py`" is verified, **Then** the verdict is `verified` and carries the chain of imports; for a
   file outside the impact it is `rejected` with the reason "not in the result".

---

### User Story 2 - A citation to code is checked against the file text (Priority: P1)

The Explorer agent claims "`AuthService` is defined in `auth/service.py` at line 12" or "`auth/service.py`
line 40 calls `hash_password`". The verifier checks that the file exists in the snapshot, that line 40 exists,
and that the line contains the symbol as a whole name. For a definition claim it also checks that the graph
lists a definition with that name, in that file, at that line.

**Why this priority**: The constitution names exactly these checks (file exists, line contains the symbol,
edge exists). Without them a model can cite a real file with an invented line, and the citation in the answer
would look trustworthy while being wrong.

**Independent Test**: For each fixture, phrase every definition of its `expected.json` as a definition claim
and check that all are verified; cite a wrong line, a missing file, a line past the end of the file and a
symbol that is not on the line, and check that each is rejected with the right reason.

**Acceptance Scenarios**:

1. **Given** `auth/service.py` defines class `AuthService` on line 12, **When** the definition claim is
   verified, **Then** the verdict is `verified` and quotes line 12 as stored for the snapshot.
2. **Given** the same file, **When** the claim cites line 13, **Then** the verdict is `rejected` with the
   reason "symbol not on the cited line" and names the line where the symbol is defined.
3. **Given** a path that is not in the snapshot, **When** any claim cites it, **Then** the verdict is
   `rejected` with the reason "file not in snapshot".
4. **Given** a file with 50 lines, **When** a claim cites line 51, **Then** the verdict is `rejected` with the
   reason "line out of range".
5. **Given** line 40 reads `hashed = hash_password_v2(pw)`, **When** a claim says the line contains
   `hash_password`, **Then** the verdict is `rejected`: a symbol matches only as a whole name, not as part of a
   longer name.
6. **Given** a snapshot whose file text is not available (a graph file without the stored analysis), **When**
   a claim needs the text, **Then** the verdict is `rejected` with the reason "file text not available", not
   `verified`.

---

### User Story 3 - Agents gather evidence through read-only tools (Priority: P2)

The agents of feature 012 need tools to explore one analyzed snapshot: find where a symbol is defined, read
lines of a file, list a file's dependents, its impact, its neighbors and the cycles in the graph. Each tool
answers from the shared graph query layer and the stored snapshot, returns a short answer that a small local
model can read, marks file text as data, and returns the citations of everything it reports so that the
agent can turn them into claims that verify.

**Why this priority**: The verifier (US1, US2) is useful on its own, for example in the benchmark (feature
016). The tools are what makes the agents possible, and most of their logic already exists in the query layer
and the MCP server (feature 006), so they come second.

**Independent Test**: Call each tool on a stored fixture snapshot and compare its facts with the same
question asked through `graphora query` or the MCP server; turn every citation a tool returns into a claim and
check that the verifier marks it `verified` (or `heuristic` where the tool marked it as likely).

**Acceptance Scenarios**:

1. **Given** a stored snapshot, **When** the agent tools are listed, **Then** each has a fixed name, a fixed
   description and typed arguments, and none of them can change the snapshot, the store or the analyzed
   repository.
2. **Given** a tool call with invalid arguments (a negative limit, an absolute path, a path with `..`, an
   unknown tool name), **When** it is made, **Then** it returns a short error message that the model can act
   on, and nothing is run.
3. **Given** a file of 5,000 lines or a dependents list of 2,000 files, **When** a tool returns it, **Then**
   the output holds at most 60 lines or 20 files and about 4,000 characters, and says that it was cut and
   how to get the rest.
4. **Given** a file whose comment says "ignore previous instructions", **When** the read-lines tool returns
   it, **Then** the text is wrapped as file content of the snapshot, marked as data, and is not treated as
   part of the tool's own message.
5. **Given** any tool answer that reports a dependency, a definition or file lines, **When** each reported
   citation is turned into a claim, **Then** the verifier marks it `verified`, or `heuristic` for links the
   tool marked as likely.
6. **Given** the same tool call made twice on the same snapshot, **When** the answers are compared, **Then**
   they are identical.

---

### Edge Cases

- A claim with no citation at all (other than a query result claim, which names a question instead) is `rejected` with the reason "no citation": it can only be a hypothesis.
- A claim that names a target in a form the graph knows (file path, node id, external package name such as
  `requests`, C# project path) is resolved the same way as in graph queries; an ambiguous or unknown target
  is `rejected` with the reason the query layer gives.
- A file that is in the snapshot but was not analyzed (`detected_only`, `not_code`, skipped) exists for text
  claims, but a dependency claim from it is `rejected` with the reason "file not analyzed".
- A dependency through a barrel (`index.ts` re-export or Python package `__init__.py`) is verified as a chain
  of its edges, not as one direct edge.
- A TypeScript `import type` link verifies, and the verdict says that it is type-only.
- A symbol given as a qualified name (`App.Models.User`, `Logger.write`) is looked up on the line by its last
  part (`User`, `write`); a definition claim compares the full name with the graph.
- Several claims are verified in one call: verdicts come back in the order of the claims, and the same input
  always gives the same verdicts.
- A malformed claim (unknown kind, line 0 or negative, empty symbol) is `rejected` with the reason "invalid
  claim" and does not stop the other claims of the same call.

## Requirements *(mandatory)*

### Functional Requirements

**Claims and verdicts**

- **FR-001**: The system MUST define a claim as: a kind, the statement it supports (free text, never parsed
  for facts), and one or more citations; a query result claim has no citation and names a graph question
  instead. A citation is a repository-relative path, a line, the snapshot id and,
  depending on the kind, a symbol or a target.
- **FR-002**: The system MUST support these claim kinds: **dependency** (a file depends on a target, cited at
  the import line), **chain** (an ordered list of dependency steps, used for transitive dependencies and
  cycles), **definition** (a named symbol is defined in a file at a line) and **mention** (a line of a file
  contains a symbol) and **query result** (a statement about the answer of a graph question: dependencies,
  dependents, impact, neighbors, cycles or key files, with its target and options; the statement is a count
  ("3 direct dependents"), a membership ("`b.py` is in the impact of `a.py`", optionally at a distance) or a
  rank ("`core.py` is among the 5 most depended-on files")).
- **FR-003**: The system MUST return one verdict per claim with a status of exactly `verified`, `heuristic`
  or `rejected`; the checks that were run with their result; for `rejected`, the first failing check and a
  reason from a fixed list (no citation, invalid claim, snapshot mismatch, file not in snapshot, file not
  analyzed, line out of range, symbol not on the cited line, no edge in the graph, edge not on the cited line,
  name not imported, import is unresolved, definition not in the graph, file text not available, count mismatch, not in the
  result, rank mismatch, plus the query layer's target errors); and, where it exists, a hint with the correct
  value (the actual import line or definition line, the actual count, distance or rank).
- **FR-004**: A `verified` verdict MUST carry the proof: the graph edges (with their full provenance) or the
  stored text of the cited line.
- **FR-005**: Only `verified` claims may be stated as facts. `heuristic` means "supported by a likely link"
  and MUST be presented as likely; `rejected` means "not proven". The verdict states this rule so that agents
  and the UI apply it the same way.

**Verification rules**

- **FR-006**: The verifier MUST be plain deterministic code: no model call, no network, no execution of the
  analyzed code. It MUST read only the snapshot's graph and the snapshot's file text from the store, never
  files on disk.
- **FR-007**: A citation MUST pass when its snapshot id equals the checked snapshot, its path is a file of the
  snapshot, and its line is between 1 and the file's line count.
- **FR-008**: A dependency claim MUST be `verified` when the graph has at least one resolved edge from the
  cited file to the claimed target on the cited line, `heuristic` when such edges exist only as heuristic
  edges, and `rejected` otherwise. Unresolved edges MUST NOT prove any target. When the claim names the
  imported name, only edges on the cited line that import that name count, matched by the same rule as the
  `symbol` filter of dependents; if none does, the claim is `rejected` with "name not imported" and a hint
  listing the names imported on that line. Without a name, any edge from the file to the target counts.
- **FR-009**: A chain claim MUST check each step as a dependency claim and take the weakest step's status; a
  rejected step names its position in the chain.
- **FR-010**: A definition claim MUST be `verified` only when the graph lists a definition with that name in
  that file at that line and the stored line contains the symbol.
- **FR-011**: A mention claim MUST be `verified` only when the stored line contains the symbol as a whole
  name (bounded by non-identifier characters), case-sensitive.
- **FR-012**: The verifier MUST resolve targets with the graph query layer and MUST NOT reimplement graph
  queries.
- **FR-012a**: A query result claim MUST be checked by running the same question with the same options
  through the graph query layer on the checked snapshot. A count is compared with the full total, never with a
  list cut by a limit. The claim is `verified` when the statement holds and every link it relies on (the
  counted items, the member's chain, the ranked file's dependents) is resolved, `heuristic` when it holds
  only with heuristic links, and `rejected` otherwise. A statement about a search that was cut by a maximum
  depth MUST say so in its options, otherwise it is checked against the full search.
- **FR-013**: The same claims against the same snapshot MUST give byte-identical verdicts when serialized.

**Agent tools**

- **FR-014**: The system MUST provide read-only agent tools over one snapshot: find definitions by name, read
  lines of a file, dependents (with an optional imported name), impact, neighbors, and cycles. Names and
  arguments MUST match the MCP tools of feature 006 where the MCP tool exists. The tools are delivered as
  plain functions without any agent-framework dependency, together with one fixed list of their names,
  descriptions and argument types; feature 012 wraps them as agent-framework tools from that list without
  adding logic.
- **FR-015**: Every tool MUST answer through the graph query layer or the store, MUST validate its arguments
  before doing anything, and MUST return an error message instead of raising for bad input or an unknown
  target.
- **FR-016**: Every tool answer MUST be trimmed to fixed bounds sized for a small local model: at most 20
  items per list, at most 60 file lines per call, and at most about 4,000 characters of text in total. The
  answer MUST say when it was cut and how to ask for the rest (a next start line or a larger offset). The
  bounds are defined in one place next to the tool list.
- **FR-017**: File text in a tool answer MUST be wrapped as marked data with its path and snapshot, separate
  from the tool's own words; tool names and descriptions MUST be fixed text that contains nothing from the
  analyzed repository.
- **FR-018**: Every tool answer MUST include, next to the short text for the model, the citations it is based
  on in the claim format of FR-001, so that an agent can attach them to a claim without retyping paths and
  lines; for file lines it returns the shown range, from which the agent builds mention claims.
- **FR-019**: Tool answers MUST keep facts and likely links apart: a heuristic link is marked as likely in
  the text, and its citation verifies as `heuristic`, never as `verified`.

**Quality**

- **FR-020**: Tests MUST cover every fixture repository: every edge and definition in its hand-written
  `expected.json`, phrased as a claim, is verified; for each of them, a claim with a changed target, line,
  path or symbol is rejected with the expected reason. Query result claims are tested on the fixtures with
  hand-checked counts, members and ranks, true and changed.
- **FR-021**: Tests MUST check that tool answers agree with the graph query layer and that every citation
  they return verifies.

### Key Entities

- **Claim**: what an agent states as a fact. Kind (dependency, chain, definition, mention, query result),
  the statement text, and citations or, for a query result, the question, target, options and the stated
  count, member or rank. The statement text is carried along but never used to decide the verdict.
- **Citation**: a pointer into the snapshot: path, line, snapshot id, and the symbol or target the line is
  said to hold. Formats as `path:line@snapshot`.
- **Verdict**: the verifier's answer for one claim: status (`verified`, `heuristic`, `rejected`), the checks
  run, a reason and hint when rejected, and the proof (edges or line text) when verified or heuristic.
- **Agent tool**: a named, read-only question about one snapshot with typed arguments, a trimmed text answer
  and the citations behind it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the edges and definitions in the hand-written `expected.json` of every fixture,
  phrased as claims, are verified.
- **SC-001a**: Every count, member and rank stated in the Reviewer example of the product context ("3 direct
  and 5 transitive dependents") can be written as a query result claim and gets a verdict.
- **SC-002**: 100% of the deliberately wrong claims (changed target, line, path, symbol, snapshot, count,
  member or rank) built
  from the same fixtures are rejected, each with the expected reason; none is verified.
- **SC-003**: No unresolved import ever leads to a `verified` or `heuristic` verdict.
- **SC-004**: Verifying the same claims twice, in the same or another process, gives identical verdicts.
- **SC-005**: Verifying 100 claims against the largest fixture snapshot takes under 1 second on a developer
  laptop, so the Reviewer adds no noticeable wait to an agent answer.
- **SC-006**: No tool answer has more than 20 items, 60 file lines or about 4,000 characters of text, and
  100% of the citations returned by tools on the fixtures verify.
- **SC-007**: In the Reviewer example from the product context ("the frontend will break" with no TS → Python
  edge), the claim is rejected with the reason "no edge in the graph".

## Assumptions

- The `Claim` and `Verdict` shapes in this spec are the proposal for the round 4 sync with feature 012; the
  review of this spec by the 012 owner is that sync, and changes agreed there are written back here before
  planning.
- File text comes only from the store (feature 005), which keeps the text of every snapshot file as it was at
  analysis time; the analyzed folder is never read. For a graph file without a stored analysis, graph checks
  (dependency, chain, query result) still run and text checks give "file text not available". Tests of text
  checks use fixture snapshots saved in the store and need PostgreSQL, like the MCP store tests of 006.
- The agent tools reuse the MCP tool names of feature 006 (`find_definitions`, `read_lines`, `dependents`,
  `impact`, `neighbors`, `cycles`) instead of the older names in the product context (`search_symbols`,
  `read_file`, `reverse_dependencies`, `impact_scope`, `detect_cycles`, `get_neighbors`). Which agent gets
  which 3–4 tools is decided in 012.
- The step budget, the revision loop, downgrading to hypotheses and the wording of answers belong to 012. 011
  only says whether a claim is proven.
- The verifier checks claims against one snapshot at a time; claims across snapshots are out of scope.
- No new HTTP endpoint, MCP tool or CLI command is added in 011; the verifier is reached through the agents
  (012) and `/ask` (013). Offering verification to external agents over MCP can be a later feature.
- The graph schema and the fixtures' `expected.json` files do not change.
