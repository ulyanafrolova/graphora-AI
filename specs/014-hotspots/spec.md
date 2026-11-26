# Feature Specification: Hotspots

**Feature Branch**: `014-hotspots`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "014 hotspots" — feature 014 from the team plan (`docs/product/team-workflow.md`,
round 5, issue #32): files that change often and have many dependents. Risk = change frequency from git history
× graph centrality, plus bus factor (how many people changed a file). Computed by code, deterministic.

## Clarifications

### Session 2026-11-26

- Q: Which history window? → A: The 12 months before the snapshot commit's date, never the current date.
- Q: Where does history come from for GitHub sources? → A: Besides the tarball, fetch only commits and trees (no
  file contents) of the snapshot commit's history over git's read-only HTTPS protocol, limited to the history
  window, within the ingest limits; no git binary is run. ZIP sources have no history.
- Q: Where is the history summary kept? → A: In the graph document (`graph.json`), with a schema version bump; the
  store saves the graph byte for byte, so stored analyses, MCP, HTTP and `graphora query` all read the same data.
- Q: What happens when reading history hits a limit? → A: A size limit (or an interrupted GitHub fetch) makes
  history "not available" with the reason. The time limit while reading commits gives a partial history: commits
  are read newest first in a fixed order, and the answer is marked partial with the number of commits read and the
  oldest commit date reached. A partial result may differ between machines; this is a recorded exception to
  determinism (constitution II) and must be justified in the plan.
- Q: Is history collected on every analysis or only on request? → A: On by default; `--no-history` (and the same
  option of an HTTP analysis job) turns it off, and then history is "not available: skipped by request".
- Q: Is the risk score commits × transitive or × direct dependents? → A: Transitive (a break spreads along import
  chains, and it matches `key_files`); direct dependents are shown alongside for information.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See the riskiest files of a snapshot (Priority: P1)

A developer analyzes a local clone of their project. Graphora reads the project's git history (without running
git or any code from the project) and, for the analyzed commit, lists the hotspots: files that were changed in
many commits and that many other files depend on. Each hotspot shows the number of commits that changed it, its
direct and transitive dependents, the number of people who changed it (bus factor) and the risk score. The top
of the list is where a change is both likely and expensive: `auth/service.py`, 47 commits, 12 transitive
dependents, bus factor 1.

**Why this priority**: This is the feature. The graph already ranks files by dependents (`key_files`); history
adds the second axis, and their product is the hotspot ranking shown in the demo (`docs/demo/README.md` § 9).

**Independent Test**: Build a small git repository in a test with a known sequence of commits by known authors,
analyze it, and compare the hotspot list (commits, authors, dependents, score, order) with hand-written expected
values.

**Acceptance Scenarios**:

1. **Given** a local git folder whose HEAD is commit `C`, where `auth/service.py` was changed in 5 commits by 1
   author and has 3 transitive dependents, **When** the hotspots of the snapshot are requested, **Then**
   `auth/service.py` is listed with 5 commits, 1 author, 3 transitive dependents and score 5 × 3 = 15.
2. **Given** two files with scores 15 and 8, **When** hotspots are listed, **Then** the file with 15 comes first;
   files with an equal score are ordered by commits, then transitive dependents, then path.
3. **Given** a file that was changed often but nothing depends on it (or a file with dependents that was never
   changed in the history window), **When** hotspots are listed, **Then** it is not a hotspot (score 0) and is
   left out of the list.
4. **Given** the same snapshot analyzed twice, **When** the hotspot results are compared, **Then** they are
   byte-identical.
5. **Given** a commit that only renames or deletes files, a merge commit, or a commit touching files outside the
   analyzed set (skipped folders, `.venv`, `node_modules`), **When** history is counted, **Then** only changes to
   files that exist in the snapshot are counted, and a merge commit is not counted on its own (its parents' commits
   are).

---

### User Story 2 - Hotspots are honest about missing history (Priority: P1)

A developer analyzes a ZIP archive, or a folder that is not a git repository. There is no history, so Graphora
says "history not available for this snapshot" instead of listing hotspots with zero commits or guessing. For a
folder with uncommitted changes the history is the history of its HEAD commit, and the answer says that local
changes are not counted.

**Why this priority**: The constitution forbids guessing (IV) and requires facts computed by code (V). A hotspot
list built from missing data would look like a fact while being wrong.

**Independent Test**: Analyze a ZIP fixture, a plain folder and a dirty git folder; check the status and the
message for each, and that no score is reported where there is no history.

**Acceptance Scenarios**:

1. **Given** a `content:` snapshot (no usable git history), **When** hotspots are requested, **Then** the answer
   states that history is not available and why, and lists no hotspots; it is not an error of the request.
2. **Given** a `<sha>+dirty:<hash>` snapshot, **When** hotspots are requested, **Then** history is read up to
   commit `<sha>` and the answer notes that uncommitted changes are not counted.
3. **Given** a GitHub URL, **When** it is analyzed, **Then** hotspots follow the rule chosen for GitHub sources:
   besides the tarball of the snapshot commit, Graphora fetches only the commits and trees of that commit's
   history within the window (no file contents) over git's read-only HTTPS protocol, and lists hotspots like for
   a local git folder.
4. **Given** a GitHub source whose history fetch fails (network error, limit exceeded), **When** it is analyzed,
   **Then** the analysis of the files still succeeds, history is "not available" with the reason, and no hotspots
   are reported.
5. **Given** a shallow clone or a history cut by the history window, **When** hotspots are listed, **Then** the
   answer reports how much history was read (number of commits, first and last commit date) so the reader knows
   the base of the numbers.

---

### User Story 3 - Agents and tools ask for hotspots and the answer verifies (Priority: P2)

A coding agent connected over MCP, a client of the HTTP API or a user of `graphora query` asks for the hotspots of
a stored snapshot and gets the same list, computed by the shared graph query layer. A claim such as
"`auth/service.py` is the top hotspot with 47 commits and bus factor 1" can be checked by the claim verifier
(feature 011) like other query result claims.

**Why this priority**: The ranking is useful already in one interface; reaching agents and the verifier makes it
usable by the hotspot explanation in the agents of 012/013 and the frontend in rounds 6–7.

**Independent Test**: For a stored fixture snapshot, request hotspots through the CLI, MCP and HTTP and compare the
answers; phrase the top hotspot's numbers as claims and check that the verifier accepts the true ones and rejects
a wrong commit count or rank with "count mismatch" / "rank mismatch".

**Acceptance Scenarios**:

1. **Given** a stored snapshot with history, **When** hotspots are requested over the CLI, MCP and HTTP,
   **Then** all three return the same items in the same order with the same numbers.
2. **Given** a hotspot claim with a wrong commit count, author count or rank, **When** it is verified, **Then**
   the verdict is `rejected` with the actual value.
3. **Given** a snapshot without history, **When** a hotspot claim is verified, **Then** it is `rejected` with the
   reason "history not available".
4. **Given** a request with a limit, **When** hotspots are listed, **Then** at most that many items are returned,
   with the total and a note that the list was cut.

---

### Edge Cases

- A file renamed during the history window: commits before the rename count toward the old path only (history is
  tracked by path, renames are not followed); the answer does not claim otherwise.
- Authors with several e-mail addresses or names are counted as different people; the same e-mail with different
  name spellings is one person. Identities are normalized by lower-case e-mail.
- Commits by bots (e.g. dependency update bots) are counted like any other; no filtering by name.
- An empty repository, a HEAD without parents, or a history with one commit: every file changed in that commit has
  1 commit; the answer is valid.
- Very long histories: reading stops at the history window. If the analysis time limit is hit while reading
  commits, the history is partial: commits are read newest first in a fixed order, so a partial history is always
  the newest part of the window; the answer is marked partial with the number of commits read and the oldest commit
  date reached, never a silently partial result.
- A shallow history (a local shallow clone, or the window boundary of a GitHub fetch): a commit whose parents are
  not available is not counted, because its change set is unknown; counting it as adding every file would invent
  churn. A true root commit (no parents in the repository) counts as adding its files.
- A GitHub history larger than the ingest size limit, or a fetch interrupted by the time limit: an interrupted
  download is not usable, so history is "not available" with the limit as the reason.
- A corrupt or unreadable `.git` folder, or a `.git` that points outside the folder (alternates, worktrees): treated
  as no history, same rule as the snapshot id.
- Files with dependents only through type-only imports: centrality follows the same `include_type_only` option as
  `key_files`.
- Commit dates in the future or out of order: the window is measured from the snapshot commit's date along the
  commit graph, not from the current time, so the result does not change over time.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST read the change history of a git working tree from its `.git` folder as data, without
  running git, hooks or any code from the repository.
- **FR-002**: For each file in the snapshot, System MUST count the non-merge commits reachable from the snapshot
  commit, within the history window, whose change set includes that path (added or modified).
- **FR-003**: For each file, System MUST count distinct authors (normalized by lower-case e-mail) of those commits;
  this number is the file's bus factor.
- **FR-004**: The history window MUST be the 12 months before the snapshot commit's commit date (a commit is in the
  window if its commit date is not earlier than that date minus 365 days), never measured from the current date.
- **FR-005**: The centrality of a file MUST be its transitive dependents as computed by `key_files`, with the same
  `include_type_only` option; direct dependents are reported alongside.
- **FR-006**: The risk score MUST be commits × transitive dependents (not direct dependents); files with score
  0 are not hotspots.
- **FR-007**: Hotspots MUST be ordered by score descending, then commits descending, then transitive dependents
  descending, then path ascending, and support a limit with total and truncation reported like other queries.
- **FR-008**: The history summary MUST be collected at analysis time and written into the graph document, so hotspots
  can be answered later without the source folder from a graph file, a stored analysis, a job result, MCP and HTTP
  alike. The graph schema version MUST be bumped and all consumers updated in the same change.
- **FR-008a**: For GitHub sources, System MUST fetch the history of the snapshot commit as commits and trees only
  (no file contents), limited to the history window, over git's read-only HTTPS protocol to the same allowed GitHub
  hosts, without running a git binary, and within the ingest size and time limits.
- **FR-009**: The history summary MUST be deterministic: same snapshot and same extractor versions give identical
  bytes; no wall-clock time, no dependency on file system or dict order. The only exception is a history marked
  partial by the time limit (FR-016).
- **FR-010**: When history is not available, System MUST report status "history not available" with a reason
  (no git folder, ZIP source, unreadable history, GitHub history fetch failed or hit a limit, skipped by request) and MUST NOT report hotspots.
- **FR-011**: The answer MUST state the base of the numbers: commits read, first and last commit date of the
  window, whether history was cut (window, shallow clone, time limit) and, for a dirty snapshot, that local changes
  are not counted.
- **FR-012**: Hotspots MUST be a query of the shared graph query layer and available through `graphora query`,
  the MCP server (read-only tool) and the HTTP API, with identical results.
- **FR-013**: The claim verifier MUST accept query result claims about hotspots (rank, commits, authors, score)
  and check them against the computed result, with the reasons used for other query claims.
- **FR-014**: Reading history MUST respect the existing analysis limits (time, size); history reading never
  follows paths outside the analyzed folder.
- **FR-015**: Author names and e-mail addresses MUST NOT be written into the graph document or exposed in hotspot
  answers; only counts are reported.

- **FR-016**: When the analysis time limit is hit while reading commits, System MUST keep the commits read so far
  (newest first, in a fixed order), mark the history `partial` with the number of commits read and the oldest
  commit date reached, and still report hotspots from it. A size limit, or a time limit during the GitHub fetch,
  makes history "not available" instead.
- **FR-017**: History MUST be collected by default on every analysis (CLI and HTTP jobs); a `--no-history` option
  of `graphora analyze`, and the same option of an HTTP analysis job, MUST skip it, and the history is then
  "not available" with the reason "skipped by request".

### Key Entities

- **History summary**: per snapshot — the snapshot commit, the window used, number of commits read, first and last
  commit date, a "cut" flag with reason, and per file: commit count and author count. Status `available`,
  `partial` (time limit, with commits read and oldest date reached) or `not_available` with a reason.
- **Hotspot**: a file with commits, authors (bus factor), direct and transitive dependents, and score; ranked.
- **Hotspot answer**: the ranked hotspots of one snapshot, with total, truncation, the history base and status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For each hand-built test history, the hotspot list (commits, authors, dependents, score, order) equals
  the hand-written expected values in 100% of cases.
- **SC-002**: Two analyses of the same snapshot that are not cut by the time limit produce byte-identical history
  summaries and hotspot answers.
- **SC-003**: Reading the history of a repository with 10,000 commits and 5,000 files adds no more than 30 seconds
  to the analysis on a developer laptop.
- **SC-003a**: For a public GitHub repository with up to 5,000 commits in the window, fetching its history adds no
  more than 60 seconds to the analysis and does not download file contents.
- **SC-004**: For every snapshot without history, 100% of hotspot requests return "history not available" with a
  reason and no numbers.
- **SC-005**: The CLI, MCP and HTTP answers for the same snapshot are identical for every fixture.
- **SC-006**: Every true hotspot claim about a fixture verifies, and every claim with one changed number is
  rejected.

## Assumptions

- Churn is counted in commits, not in changed lines: simpler, deterministic and matches the demo ("47 commits").
- Renames are not followed; history is tracked by path (a known limitation, documented in the answer's notes).
- Merge commits are not counted on their own; first-parent comparison is not used, all non-merge commits reachable
  from the snapshot commit are.
- Bus factor is the number of distinct authors; more refined measures (main author share, knowledge loss) are out
  of scope.
- Clustering, the visual hotspot map (treemap) and agent explanations of hotspots belong to the frontend (rounds
  6–7) and agents (012/013); this feature only provides the computed facts.
- The existing git reading library used for the snapshot id is reused for both local history and the GitHub fetch;
  no new runtime services and no git binary.
- The history of a commit is immutable, so a GitHub fetch at different times gives the same summary for the same
  snapshot; only a failed fetch changes the result, and it is marked as such.
- Only public GitHub repositories are supported, as in feature 002; no tokens.
- Fixtures cannot hold a nested `.git` folder in this repository, so tests build git histories at test time.
