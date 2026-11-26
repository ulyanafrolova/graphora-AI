---

description: "Task list for 011-claim-verifier"
---

# Tasks: Claim Verifier and Agent Tools

**Input**: Design documents from `specs/011-claim-verifier/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R11), data-model.md, contracts/verifier.md,
contracts/agent-tools.md, quickstart.md

**Tests**: Required (constitution VIII, spec FR-020, FR-021). Within each phase, write the tests first and
confirm they fail.

**Organization**: Phase 2 (claim and verdict types, `matches_symbol`) blocks every story. Then:

- US1 (P1): dependency, chain and query result claims checked against the graph;
- US2 (P1): definition and mention claims checked against the stored file text;
- US3 (P2): read-only agent tools that return ready-to-verify claims.

Paths are relative to the repository root. Code lives in `backend/src/graphora/`, tests in `backend/tests/`.
Run commands from `backend/`. Keep comments minimal, in the style of the existing modules (one short module
docstring with a spec reference, one-line docstrings only where not obvious). Tests take claims from the
hand-written `expected.json` and `queries.json`, never from verifier output.

**Commits**: commit after each task group marked **Commit** (several per phase); push at the end of each
phase. Messages short, lowercase, English.

## Phase 1: Setup

- [ ] T001 Rename `_matches` to public `matches_symbol` in `backend/src/graphora/graph/queries.py` (update its
  one caller in `dependents`; behaviour unchanged) and run `uv run pytest tests/unit/test_dependents.py`.
- [ ] T002 Create the packages `backend/src/graphora/verify/__init__.py` and
  `backend/src/graphora/tools/__init__.py`, each with a one-line module docstring referencing
  `specs/011-claim-verifier`.

**Commit**: `public matches_symbol, verify and tools packages`

---

## Phase 2: Foundational (claim and verdict types)

**Purpose**: the shared types all three stories use (data-model.md, contracts/verifier.md).

- [ ] T003 [P] Write `backend/tests/unit/test_verify_claims.py`: `Claim.from_dict`/`to_dict` round trip for
  every JSON example of `contracts/verifier.md`; `to_dict` drops `None` fields; `Claim.cite()` gives
  `path:line@snapshot` (first step for chains); `validate(claim)` returns an error for each rule of
  data-model.md § Claim validation: a dependency/chain claim with no steps or a definition/mention claim
  without path → `no_citation` (checked first, no other error), query claims never `no_citation`; unknown kind, fields of another kind present, line < 1, empty
  path/symbol/target, a dependency with other than 1 step, a chain with < 2 steps or unconnected steps,
  query option key not allowed for the question, not exactly one of `count`/`member`/`rank`, `distance`
  without `member` or outside `impact`, `rank` outside `key_files`, `target` None for a question other than
  `cycles`/`key_files`; `Verdict.to_dict()` writes `fact` as `status == "verified"`, proof items as
  `{"kind": "edge", …}` / `{"kind": "line", …}`; `dumps(verdicts)` is byte-identical on two calls and ends
  with a newline.
- [ ] T004 Implement `backend/src/graphora/verify/claims.py`: frozen dataclasses `Step(path, line, target,
  name=None)`, `Claim` (fields of data-model.md § Claim; `kind` one of `dependency | chain | definition |
  mention | query`; `question` one of `dependencies | dependents | impact | neighbors | cycles | key_files`),
  `Check(name, ok, detail)`, `Line(path, n, text)`, `Verdict(status, checks, reason=None, hint=None,
  step=None, proof=())` with property `fact`; `Reason` Literal with exactly the 17 codes of data-model.md §
  Reasons; `ALLOWED_OPTIONS` per question (`include_type_only`, `follow_barrels`, `symbol` only for
  dependents, `max_depth` only for impact, `level` for dependencies, dependents, impact, cycles);
  `validate(claim) -> str | None`; `from_dict`, `to_dict`, `cite`; `dumps(verdicts)` with
  `json.dumps(sort_keys=True, ensure_ascii=False, indent=2) + "\n"`; edges in proof serialized with
  `graph.serialize._edge_dict`.
- [ ] T005 Export `Claim`, `Step`, `Verdict`, `Check`, `Line`, `dumps` from
  `backend/src/graphora/verify/__init__.py`; run `uv run pytest tests/unit/test_verify_claims.py`.

**Commit**: `claim and verdict types`

**Checkpoint**: push.

---

## Phase 3: User Story 1 — A dependency claim is checked against the graph (Priority: P1) 🎯 MVP

**Goal**: dependency, chain and query result claims get `verified`, `heuristic` or `rejected` from the graph
alone (spec US1, FR-002, FR-003, FR-008, FR-009, FR-012, FR-012a, FR-013; research R5, R7).

**Independent Test**: every edge of every fixture's `expected.json` as a dependency claim gets the status of
its confidence; every `queries.json` entry as count and member claims verifies; mutations are rejected with
the expected reason — all without a database.

### Tests for User Story 1

- [ ] T006 [P] [US1] Write `backend/tests/unit/test_verify_graph.py` on graphs from
  `tests/unit/synthetic.py`, one test per rule:
  resolved edge at the cited line → `verified`, `fact` true, proof = that edge; same claim on another line →
  `edge_not_on_line`, hint `edge on line 3` (`edges on lines 3, 9` for two); no edge → `no_edge`; only a
  heuristic edge → `heuristic`; resolved + heuristic edges on the line → `verified`; an unresolved import on
  the cited line and no edge to the target → `import_unresolved`; name matching (`matches_symbol`, incl. a
  re-export alias and a C# full type name) → `verified`, wrong name → `name_not_imported`, hint
  `imported on line 3: a, b`; no name → any edge counts; source `detected_only` → `file_not_analyzed`;
  unknown source path → `file_not_in_snapshot`; unknown target → `target_not_found` with the `NodeNotFound`
  message as hint; snapshot ≠ graph snapshot → `snapshot_mismatch`; invalid claim → `invalid_claim` and the
  next claim in the same call still verified; `project:`/`solution:` source → verified; type-only edge →
  verified and its check detail says `type-only`; chain of 3 steps all resolved → `verified`, one heuristic
  step → `heuristic`, step 2 wrong → `rejected` with `step` 2; closed chain (cycle) → `verified`;
  query claims: dependents count (`count_mismatch`, hint `actual 3`), impact member with distance
  (`not_in_result`, hint `at distance 1`), impact with `max_depth`, neighbors member in incoming or outgoing,
  cycles count and member, key_files rank (`rank_mismatch`, hint `rank 7` / `not ranked`), heuristic item →
  `heuristic`, count ignores any `limit` (full total); verdicts come back in claim order and `dumps` is equal
  on two runs.
- [ ] T007 [P] [US1] Write `backend/tests/golden/test_verify_fixtures.py` (no `db` mark), parametrized over
  every fixture with `expected.json`, using `analyze_fixture` from `conftest.py` and `queries.index`:
  each non-unresolved edge → dependency claim (`path` = source id without its kind prefix, `line`, `target` =
  target id, `name` = edge `symbol`) gets `verified` for `resolved`, `heuristic` for `heuristic`; each
  unresolved edge → claim on its `unresolved:` target is never `verified`/`heuristic` (SC-003);
  mutations of each resolved edge: line → a line with no edge between the pair (`edge_not_on_line`), target →
  a file with no edge from the source (`no_edge`; skip when none exists), path → `missing/x.py`
  (`file_not_in_snapshot`), snapshot → `other` (`snapshot_mismatch`), name → `NoSuchName`
  (`name_not_imported`, when the edge has a symbol); each `queries.json` entry with a question supported by
  query claims: count claim with `total` (or the number of items/groups) → verified or heuristic, count + 1 →
  `count_mismatch`; each item `node` (or group file for cycles) → member claim with its `distance` when given
  → not rejected; a file of the fixture not in the result → `not_in_result`. Entries with `projects` are
  skipped.

### Implementation for User Story 1

- [ ] T008 [US1] Implement dependency and chain checks in `backend/src/graphora/verify/graph_checks.py`
  following research R5 exactly: resolve the source with `queries.resolve` (status `not_in_snapshot` →
  `file_not_in_snapshot`; `detected_only`, `not_code` or a skip reason → `file_not_analyzed`; other →
  `invalid_claim`); the source node must be `file:`, `project:` or `solution:`; resolve the target
  (`NodeNotFound` → `target_not_found`, message as hint); take the pair's edges from `ix.links`
  (empty when there is no link); none → `import_unresolved` if `ix.unresolved[source]` has an edge on the
  cited line, else `no_edge`; filter by line → `edge_not_on_line`; filter by `queries.matches_symbol` when
  `name` is set → `name_not_imported`; status `verified` if any remaining edge is resolved else `heuristic`;
  proof = remaining edges sorted by `edge_sort_key`; a chain runs each step and takes `results.weakest`,
  stopping at the first rejected step with `step` set. Checks named as in data-model.md § Verdict.
- [ ] T009 [US1] Implement `verify(claims, ix, text=None)` in `backend/src/graphora/verify/__init__.py`:
  for each claim in order, `validate` → `invalid_claim`; snapshot check → `snapshot_mismatch`; dispatch by
  kind; definition and mention claims return `rejected` / `text_unavailable` until US2. Run
  `uv run pytest tests/unit/test_verify_graph.py -k "not query"`.

**Commit**: `dependency and chain checks`

- [ ] T010 [US1] Add query result checks to `backend/src/graphora/verify/graph_checks.py` (research R7):
  call `queries.dependencies | dependents | impact | neighbors | cycles | key_files` with the claim's options
  and `limit=None` (key_files: `limit=None` too); `NodeNotFound` → `target_not_found`, `ValueError` →
  `invalid_claim`; count vs `Answer.total` → `count_mismatch` (hint `actual N`); member resolved with
  `queries.resolve`, looked up in `items`, `incoming` + `outgoing` (neighbors) or group `files` (cycles),
  `distance` compared for impact → `not_in_result` (hint `at distance D` when present elsewhere); rank =
  1-based position in key_files items ≤ `rank` → else `rank_mismatch` (hint `rank P` or `not ranked`);
  status: count → `heuristic` if any counted item (or group) is heuristic, member → the item's confidence,
  rank → `heuristic` if any item of `queries.impact(ix, member)` is heuristic; proof = the member item's chain
  edges, else empty. Run `uv run pytest tests/unit/test_verify_graph.py tests/golden/test_verify_fixtures.py`.

**Commit**: `query result claims`

**Checkpoint**: US1 complete without a database. Push.

---

## Phase 4: User Story 2 — A citation to code is checked against the file text (Priority: P1)

**Goal**: definition and mention claims are checked against the store's file text (spec US2, FR-007,
FR-010, FR-011, clarification "store only"; research R6).

**Independent Test**: with a fake text source, every rule of R6 gives the expected reason; on stored fixtures
every `expected.json` definition verifies and its mutations are rejected.

### Tests for User Story 2

- [ ] T011 [P] [US2] Write `backend/tests/unit/test_verify_text.py` with a fake `TextSource` (a dict of
  path → `store.FileText`) over a synthetic graph: mention of a whole name → `verified`, proof = `Line`;
  `hash_password` on a line with `hash_password_v2(pw)` → `symbol_not_on_line`; `$el` matched in JS text;
  case differs → rejected; qualified `Logger.write` / `App.Models.User` matched by last part; line 51 of a
  50-line file → `line_out_of_range`; path not in coverage → `file_not_in_snapshot`; a `not_code` file in
  coverage is fine for mention; no text source, or `FileText.has_text` false → `text_unavailable`;
  definition in the graph at the line → `verified`; definition at another line → `symbol_not_on_line`,
  hint `defined on line 12`; name not defined in the file → `definition_not_in_graph`; mention not on the
  line but on line 14 → hint `found on line 14` (nearest line, lower line wins a tie); the text source is
  read once per file within one `verify` call.
- [ ] T012 [P] [US2] Write `backend/tests/golden/test_verify_store.py` marked `db`: store every fixture
  (`store.put(name, analyze_fixture(name))`), `from_store(database_url, name, snapshot)`, then for every
  definition in `expected.json` a definition claim (`symbol` = definition name) → `verified`; line + 1 →
  `symbol_not_on_line` unless the name also appears there; symbol `NoSuchName` → `definition_not_in_graph`;
  path `missing/x.py` → `file_not_in_snapshot`; a mention claim of the definition's last name part on its
  line → `verified`. If any hand-written definition line does not contain its name, stop and report it
  instead of loosening the rule.

### Implementation for User Story 2

- [ ] T013 [US2] Implement `backend/src/graphora/verify/text_checks.py` (research R6): `TextSource`
  protocol `get(path) -> FileText | None`; `store_text(store, repository, snapshot)` reading whole files with
  `Store.get_file` and caching per instance; `_has_name(line, name)` with
  `re.search(rf"(?<![\w$]){re.escape(last)}(?![\w$])", line)` where `last` is the part after the final `.`;
  `check_mention` and `check_definition` with checks `file`, `text`, `range`, `definition`, `symbol` and the
  reasons and hints listed in T011; definitions looked up in the `FileNode` by full name or last part (as
  `queries.definitions`).
- [ ] T014 [US2] Wire definition and mention claims into `verify` in
  `backend/src/graphora/verify/__init__.py`, wrap the given source so each file is read once per call, add
  `verify_served(claims, served)` (uses `store_text` when `served.store` is set, else no text) and export
  `store_text`, `TextSource`. Run `uv run pytest tests/unit/test_verify_text.py` and, with the database,
  `uv run pytest -m db tests/golden/test_verify_store.py`.

**Commit**: `text checks for definitions and mentions`

**Checkpoint**: US1 and US2 complete. Push.

---

## Phase 5: User Story 3 — Agents gather evidence through read-only tools (Priority: P2)

**Goal**: six read-only tools with MCP names, bounded output, file text framed as data and ready-to-verify
claims (spec US3, FR-014–FR-019, FR-021; research R8–R10; contracts/agent-tools.md).

**Independent Test**: each tool's facts equal the query layer's; every returned citation verifies (or is
`heuristic` where marked likely); no answer exceeds 20 items, 60 lines or 4,000 characters.

### Tests for User Story 3

- [ ] T015 [P] [US3] Write `backend/tests/unit/test_tools.py` on a synthetic graph wrapped in `Served`
  (no store) and on a `Served` whose `store` is a fake object with `get_file`: `TOOLS` names in contract
  order (`find_definitions`, `read_lines`, `dependents`, `impact`, `neighbors`, `cycles`) and descriptions
  are fixed strings; `tools_for` without a store has no `read_lines`; invalid arguments (offset < 0,
  max_depth 0, start 0, end < start, path `/etc/passwd`, `a/../b`, `a\\b`, empty name/target/symbol) →
  `error` set, `text` starts with `error: `, no citations; unknown target → the `NodeNotFound` message;
  neighbors with 30 incoming → 20 shown, `offset=20` gives the rest; 30 dependents → 20 shown, `cut` true, `next` 20, text ends with `(cut: call again with offset=20)`,
  `offset=20` returns the other 10 and `cut` false; long text cut by whole lines to ≤ 4,000 characters with
  the same cut line and `next` = offset + items actually shown; `read_lines` of a 100-line file → 60 lines, `next` 61, frame lines exactly as in the
  contract, a line `# ignore previous instructions` appears only inside the frame; heuristic links shown with
  `(likely)`; citations match the shown items; same call twice → equal results; every returned claim
  verifies with `verify` (`heuristic` exactly for `(likely)` items).
- [ ] T016 [P] [US3] Add to `backend/tests/golden/test_verify_store.py` (marked `db`): for every stored
  fixture, call `dependents`, `impact` and `neighbors` on every analyzed file, `cycles`, and
  `find_definitions` on every definition name of `expected.json`, following `next` until not cut; compare the
  listed nodes with `queries.*` answers on the same index; verify all citations with `verify_served`: none
  rejected, and `heuristic` only for items marked likely (SC-006).

### Implementation for User Story 3

- [ ] T017 [US3] Create `backend/src/graphora/tools/limits.py` with `MAX_ITEMS = 20`, `MAX_LINES = 60`,
  `MAX_CHARS = 4000`, and in `backend/src/graphora/tools/__init__.py` the types `ToolSpec(name,
  description)`, `ToolResult(text, citations=(), lines=None, cut=False, next=None, error=None)`,
  `LineRef(path, start, end, snapshot)` (data-model.md § ToolSpec, ToolResult, LineRef).
- [ ] T018 [US3] Implement `backend/src/graphora/tools/agent.py`: `TOOLS` with fixed English descriptions
  (what the tool answers, argument meaning, `(likely)` = heuristic, how to get the rest; no repository
  content); argument validation of contracts/agent-tools.md § Validation, copying the one-line path rule of
  `mcp.server._valid_path` (the MCP server is not changed); list tools compute the answer with `limit=None`, slice
  `offset … offset + MAX_ITEMS` into a copy of the `Answer` (neighbors: the same slice of each list), render with
  `results.render_text`, cut by whole lines to `MAX_CHARS`, append the cut line with `next` = offset + items actually shown; `read_lines` reads
  `Store.get_file(repository, snapshot, path, start, start + MAX_LINES - 1)` and frames the text exactly as
  the contract; errors become `ToolResult(text="error: …", error=…)`.
- [ ] T019 [US3] Add citations in `backend/src/graphora/tools/agent.py` (research R10): a link without `via`
  → dependency claim on its first edge (`path`, `line`, `target`, `name` = edge symbol); a link with `via`
  (barrel) → chain claim through the re-exporting files; impact item → chain along its chain (dependency at
  distance 1); cycle group → closed chain; definition match → definition claim; `read_lines` → `LineRef`.
  Only shown items get citations; `statement` is empty and `snapshot` is the served snapshot.
- [ ] T020 [US3] Implement `tools_for(served)` in `backend/src/graphora/tools/__init__.py` returning a dict
  of typed closures named as in `TOOLS` (`read_lines` only when `served.store` is set). Run
  `uv run pytest tests/unit/test_tools.py` and, with the database, `uv run pytest -m db
  tests/golden/test_verify_store.py`.

**Commit**: `agent tools` (split into `tool types and limits`, `agent tools`, `tool citations` if the
changes are large)

**Checkpoint**: all stories complete. Push.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T021 [P] Write `backend/tests/integration/test_verify_performance.py` marked `slow`: 100 claims (mixed
  kinds, built from `expected.json` of the fixture with the most edges) verified against the stored snapshot
  in under 1 second, excluding storing (SC-005); marked `db` too.
- [ ] T022 [P] Add a determinism test to `backend/tests/golden/test_verify_fixtures.py`: verdicts for all
  fixture claims serialized with `dumps` are byte-identical across two runs in separate processes
  (`subprocess` running `python -c` over one fixture) (SC-004, FR-013).
- [ ] T023 [P] Add the Reviewer example to `backend/tests/unit/test_verify_graph.py`: a synthetic graph with
  `frontend/login.ts` and `auth/service.py` and no edge between them; the claim "frontend depends on
  auth/service.py" → `no_edge` (SC-007).
- [ ] T024 Run `make check` from the repository root (with `make db` and `GRAPHORA_TEST_DATABASE_URL`); fix
  ruff findings.
- [ ] T025 Walk through `specs/011-claim-verifier/quickstart.md` manually and fix any step that does not
  match; update the PR #30 description (status checkboxes, how to try it).

**Commit**: `performance and determinism tests`, then `quickstart fixes` if needed. Push and mark PR #30 ready
for review after Ulyana has seen the contracts.

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → stories. Phase 2 (types) blocks everything.
- US1 (Phase 3) needs only Phase 2. US2 (Phase 4) needs `verify()` from T009. US3 (Phase 5) needs `verify`
  for its tests (T015, T016) and both US1 and US2 for citations to verify; its implementation (T017–T020)
  can start after Phase 2.
- Polish after all stories.

### Within each story

Tests first (they fail), then implementation, then run the tests, then commit.

### Parallel opportunities

- T003 alongside T001–T002.
- US1: T006 and T007 together. US2: T011 and T012 together. US3: T015 and T016 together.
- After T009, US2 (T011–T014) and US3 implementation (T017–T020) touch different files and can go in
  parallel.
- Polish: T021, T022, T023 together.

## Parallel Example: User Story 1

```text
T006 tests/unit/test_verify_graph.py        (synthetic rules)
T007 tests/golden/test_verify_fixtures.py   (expected.json / queries.json)
```

## Implementation Strategy

### MVP (User Story 1)

Phases 1–3: dependency, chain and query result claims verified from the graph alone. This already lets 012
build its Reviewer on the real verifier and lets the 016 benchmark check claims, without a database.

### Incremental delivery

1. Phase 1–2 → types agreed with 012 are in code.
2. US1 → graph claims (MVP). Push.
3. US2 → text claims with the store. Push.
4. US3 → agent tools for 012. Push.
5. Polish → performance, determinism, `make check`, PR ready.
