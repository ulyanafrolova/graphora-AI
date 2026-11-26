# Feature Specification: Web UI

**Feature Branch**: `019-frontend`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "019 frontend, issue #40" — the whole web UI of `docs/demo` (§ 1–9 and § 12) in one
feature and one pull request (team agreement), built on the stored-snapshot HTTP API, plus the backend additions
the screens need: components (community detection with a fixed seed, named after their common folder), a
deterministic cycle cut suggestion, and per-file line counts. § 10 PR impact and § 11 Security are shown as "not
available in this version". The mockups in `docs/demo/*.png` are the reference for layout and visual language; their
numbers and file names are illustrative.

## Clarifications

### Session 2026-11-26

- Q: By which rule does Graphora pick the link(s) to suggest removing in a cycle? → A: A minimum feedback arc set
  (the fewest links whose removal leaves no cycle in the group), computed exactly for groups of up to 20 files; larger
  groups use the greedy rule (the link that breaks the most cycles, then the fewest imported names, then path order,
  repeated until no cycle is left). The answer says which method was used.
- Q: From what snapshot size does the graph open with collapsed components? → A: Always: every snapshot opens at the
  System level (components collapsed), whatever its size; the user expands components or switches to File level.
- Q: How do users open the UI? → A: A development server for UI work, and `graphora serve` also serves the built UI
  from the same address as the API when a build is present, so a demo needs one command and one address.
- Q: Are agent answers and traces kept after a page reload? → A: Yes, in the user's browser only: the last 20 answers
  with their traces per snapshot, with a "clear history" action; nothing is stored on the server.
- Q: How is a component named when its files share no folder, or two components get the same name? → A: The longest
  common folder; if none, the most frequent top-level folder among its files (ties by path order); equal names get
  ` · 2`, ` · 3`, … in the order of each component's first file path.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Explore a stored snapshot: graph, impact and code (Priority: P1)

A developer opens Graphora in the browser and picks an analyzed repository and snapshot. The dependency graph
appears (`docs/demo` § 2, `02-graph.png`): files grouped into components, edge width by number of imports, heuristic
links (for example frontend → backend HTTP routes) dashed in amber, cycle links in red, and a legend that says so.
Clicking a file selects it: a side panel shows what it depends on, what uses it, its rank among key files and its
issues (cycles it is in). Impact mode highlights every file that a change could affect, counts them per component,
and shows heuristic impact apart (§ 4, `12-large-graph-zoom.png`). From the panel the developer opens the code view
(§ 5, `03-code-provenance.png`): the file tree, the numbered lines of the file with markers on import lines, and for
the selected import the edge provenance (source `file:line@commit`, type and imported name, confidence, extractor
and version, snippet hash), plus the outgoing and incoming links with their confidence.

**Why this priority**: This is the core value of the product in the browser: a pinned, cited dependency graph that
answers "what breaks if I change this file". Every other screen builds on the same shell, snapshot selection and
graph.

**Independent Test**: Store a fixture repository, open the UI, select a known file, and check that the highlighted
impact set, the neighbour lists and the provenance of one import equal the API answers for that snapshot.

**Acceptance Scenarios**:

1. **Given** at least one stored snapshot, **When** the user opens the UI, **Then** they can choose a repository and
   snapshot, and the header shows `repository @ short commit`, one badge per language with its analysis status
   (analyzed, detected only) and the configured model.
2. **Given** an open snapshot, **When** the graph view is shown, **Then** every drawn link is a link of the stored
   graph, heuristic links are drawn dashed and amber, cycle links red, and a legend explains both.
3. **Given** a selected file, **When** impact mode is on, **Then** exactly the files of the impact answer are
   highlighted, the panel shows the total and the count per component, heuristic impact is labelled as such, and a
   cut answer says so ("and N more").
4. **Given** a selected file, **When** the code view opens, **Then** its lines are shown exactly as stored (as text,
   never interpreted), import lines are marked, and selecting one shows that edge's full provenance.
5. **Given** a link whose target was not resolved, a file that was only detected or skipped, or an external package,
   **When** it is shown, **Then** it is labelled as such and never drawn as a resolved file link.
6. **Given** a link to the selected state of the UI (repository, snapshot, view, selected file), **When** it is opened
   in another browser tab, **Then** the same view appears.

---

### User Story 2 - Import a repository and follow the analysis (Priority: P1)

A developer pastes a public GitHub URL (optionally a branch, tag or commit) or drops a ZIP archive on the Import
screen (§ 1, `01-import.png`). The analysis starts; the screen shows its stage (queued, resolving the commit,
fetching, analyzing, storing, done or failed), the commit it is pinned to, the safety limits (size, files, time,
skipped folders, "never executed — static analysis only"), and when it is done the language coverage (files per
language, share, depth: full, detected only, not code). One click opens the new snapshot in the graph view.

**Why this priority**: Without import a user can only see snapshots that someone stored from the command line; this
is the entry point of the demo.

**Independent Test**: Start an import of a fixture ZIP from the UI, follow it to done, open the graph; start one that
fails a limit and check the failure is shown with its reason.

**Acceptance Scenarios**:

1. **Given** a GitHub URL, **When** the user starts the analysis, **Then** the job's stage is shown and updated until
   it is done or failed, without reloading the page.
2. **Given** a ZIP file, **When** it is dropped or chosen, **Then** it is uploaded and followed the same way.
3. **Given** a job that fails (invalid URL, not found, too large, too many files, time limit, unsafe archive),
   **When** it ends, **Then** the reason is shown in plain words and the user can try again.
4. **Given** the same source analyzed before, **When** it is imported again, **Then** the existing analysis is reused
   and opened without waiting for a new analysis.
5. **Given** the service has too many jobs queued, **When** the user starts one, **Then** they are told to try later.

---

### User Story 3 - Insights: cycles, hotspots, key files and search (Priority: P2)

From the sidebar the developer opens Cycles (§ 8, `06-cycles.png`): every group of files that import each other in
a loop, with the number of links, an example cycle of import lines, and the suggested links to remove — the fewest
links whose removal ends every loop of the group, with their lines — shown as "recommendation only; Graphora never
modifies your code". Hotspots (§ 9, `07-hotspots.png`) shows a risk map where tile size is lines of code and colour
is the risk score, and a table of top risks with commits, transitive dependents ("used by") and bus factor, with the
history base (window, commits read) or "history not available" with the reason. A search box finds files by path and
symbols by exact name and opens the file in the graph or code view.

**Why this priority**: These screens turn the graph into decisions (what to refactor, what to test first); they reuse
the shell and graph of US1.

**Independent Test**: On a fixture with known cycles and a git history, compare the cycles list, the suggested cut,
the hotspot table and the search results with the API answers.

**Acceptance Scenarios**:

1. **Given** a snapshot with cycles, **When** Cycles is opened, **Then** each group is listed with its files, link
   count and example cycle, and a selected group shows the suggested links to remove with file, line and line text,
   the method (exact or greedy), labelled as a recommendation.
2. **Given** a type-only cycle, **When** it is listed, **Then** it is marked as not failing at run time.
3. **Given** a snapshot with history, **When** Hotspots is opened, **Then** tiles are sized by lines of code and
   coloured by score, and the table lists commits, used by and bus factor as numbers only (no names or e-mails).
4. **Given** a snapshot without history (ZIP, plain folder, skipped), **When** Hotspots is opened, **Then** it says
   "history not available" and why, and shows no tiles.
5. **Given** a search for a file path or a symbol name, **When** a result is chosen, **Then** that file is selected
   in the graph; a name that is defined nowhere shows "no definitions", not an error.

---

### User Story 4 - Ask agents and follow the trace (Priority: P2)

On Ask agents (§ 6, `04-ask-agents.png`) the developer types a question ("What breaks if I change AuthService?") or
picks a suggested one. While the agents work, their steps appear live; the answer then shows verified facts with
`file:line@commit` citations, cycle warnings, and hypotheses in a separate amber "not statically proven" style. The
files the answer cites are highlighted in a small graph next to it, and one click opens them in the main graph.
Agent trace (§ 7, `05-agent-trace.png`) shows the full run: each step with the agent role, the tool and its
arguments, a short result and its duration, revisions requested by the reviewer, the claims with their status
(verified, rejected, hypothesis) and the step budget used (tool calls, revisions).

**Why this priority**: The agents are a key differentiator, but they need the graph screens to point into, and they
depend on a local model that may be absent.

**Independent Test**: With the scripted test model, ask a question from the UI and check that the live steps, the
final facts and hypotheses, the citations and the trace equal the streamed events and answer.

**Acceptance Scenarios**:

1. **Given** a question, **When** it is sent, **Then** each step appears as it is streamed, and the final answer
   replaces the progress view.
2. **Given** an answer, **When** it is shown, **Then** verified facts and hypotheses are visually distinct, every
   fact has its citation, and agent text is shown as text, never as markup or links that run anything.
3. **Given** another question is being answered (busy) or the model is not available, **When** the user asks,
   **Then** they see that message and can retry; the page does not hang.
4. **Given** a finished answer, **When** Agent trace is opened, **Then** the steps, claim statuses and budget of that
   run are shown.
5. **Given** finished answers, **When** the page is reloaded, **Then** the last 20 answers of the snapshot and their
   traces are still listed; "clear history" removes them.

---

### User Story 5 - Large repositories stay readable (Priority: P3)

A repository with about 5,000 files opens in the overview (§ 3, `11-large-graph-overview.png`): components are shown
collapsed, each with its name and file count, sized by dependents, links between components bundled, links with a
cycle red, and hotspots marked. A panel shows files, links, components and cycles. Clicking a component expands it
to its files while the others stay collapsed (§ 4), with a breadcrumb ("System › Auth (31 of 38 files shown)") and
a minimap of the whole repository. Filters hide test files and external packages. The current view can be exported as
an image.

**Why this priority**: Needed for real repositories, but the small and medium cases of US1 already deliver value.

**Independent Test**: Store a 5,000-file graph, open it, expand and collapse a component, and measure that the view
stays responsive.

**Acceptance Scenarios**:

1. **Given** any snapshot, **When** its graph is opened, **Then** components are collapsed (System level) and the
   counts in the panel equal the API answers.
2. **Given** a collapsed component, **When** it is clicked, **Then** its files appear and its links to other
   components stay bundled.
3. **Given** a selected file in an expanded component, **When** impact mode is on, **Then** affected files in
   collapsed components are counted on the component, not drawn one by one.
4. **Given** the minimap, **When** the user moves the frame, **Then** the main view follows.

---

### User Story 6 - Connect a coding agent over MCP; honest placeholders (Priority: P3)

MCP for agents (§ 12, `10-mcp.png`) explains how to connect Claude Code or Cursor to `graphora mcp` for the open
snapshot, with copyable configuration, the list of read-only tools as the server actually exposes them, and an
example. PR impact and Security stay in the navigation and open a page that says they are not available in this
version, without sample data.

**Why this priority**: Static content; it completes the demo but carries no analysis.

**Independent Test**: Open both pages; check the commands and tool names match the MCP server, and that the
placeholder pages contain no numbers.

**Acceptance Scenarios**:

1. **Given** an open snapshot, **When** MCP for agents is opened, **Then** the shown commands name that repository
   and snapshot and can be copied.
2. **Given** PR impact or Security, **When** opened, **Then** the page states "not available in this version" and
   shows no graph, numbers or file names.

---

### Edge Cases

- No stored snapshot yet: the UI opens on Import with a short explanation.
- The service or its store is down: every screen shows a clear "service unavailable" state with retry, never an
  empty graph that looks like a fact.
- A stored analysis with an older graph schema (`stale`): the UI says it must be analyzed again and offers import.
- A file whose content is binary, very long or not stored: the code view says so instead of showing broken text.
- File contents, file names, commit messages, agent answers and repository names containing markup or script: shown
  literally as text.
- A graph with no links, a repository with one file, a snapshot with only detected-only languages: valid, labelled
  views.
- Impact or cycle answers cut by the limit: the UI states the total and that the list is cut.
- A selected file disappears when switching snapshots: the selection is cleared with a note.
- Two browser tabs on different snapshots: each shows its own snapshot.
- The model badge when no model is configured: "agents off" instead of a model name; Ask agents explains how to
  enable it.
- A cycle group larger than 20 files: the suggestion uses the greedy rule and is labelled as such; it may remove more
  links than strictly necessary.
- A browser that refuses to store the history (private mode, storage full): answers still work, and the UI says the
  history will not be kept.
- Files at the repository root (no folder): they count as the top-level folder `.` for naming, so a component of
  root files is named `.`.
- Hotspot history `partial` or with uncommitted local changes: the notes of the answer are shown next to the map.

## Requirements *(mandatory)*

### Functional Requirements

**Shell and navigation**

- **FR-001**: The UI MUST have the layout of the mockups: a header (product name, `repository @ short commit`
  selector, language status badges, model badge), a sidebar with sections Project (Import, Dependency graph, Code &
  provenance), AI agents (Ask agents, Agent trace), Insights (Cycles, Hotspots, PR impact, Security) and
  Integrations (MCP for agents), and the footer note "Code is never executed. Read-only agents."
- **FR-002**: The repository, snapshot, current screen, view level and selected file MUST be reflected in the page
  address, so a link reopens the same view.
- **FR-003**: Every number, list and link the UI shows about a snapshot MUST come from an answer of the Graphora
  service; the UI MUST NOT compute dependencies, impact, cycles, components, centrality, hotspots or claim statuses
  itself (constitution V, VII). Drawing, layout, filtering what is shown and folding components are view operations.
- **FR-004**: Resolved, heuristic and unresolved links MUST be visually distinct everywhere they appear (graph,
  panels, code view, agent answers), and every screen with such marks MUST have a legend (constitution IV).
- **FR-005**: File contents, paths, symbol names, agent text and any other text from the analyzed repository or the
  model MUST be displayed as plain text; it MUST NOT be interpreted as markup, executed, or turned into active links
  other than links to views of the same snapshot (constitution I, VI).
- **FR-006**: Service errors (not found, stale, busy, model unavailable, store unavailable, too many jobs) MUST each
  be shown with a plain message and a next step (retry, analyze again, import).

**Graph, impact and code (US1, US5)**

- **FR-007**: The graph view MUST offer the levels System (components), Component (one component expanded to files)
  and File, filters for test files and external packages, and a search box.
- **FR-008**: Selecting a file MUST show its direct dependencies and dependents, its key-file rank, and the cycles it
  belongs to; selecting a component MUST show its file count, lines of code, links in and out, key files and issues.
- **FR-009**: Impact mode MUST highlight the impact answer of the selected file, show the total, the count per
  component and the heuristic part separately, and state when the answer is cut.
- **FR-010**: The code view MUST show a file tree of the snapshot, the stored lines of the selected file with line
  numbers, markers for lines that carry links, and for a selected link its provenance (source file and line, commit,
  type, imported name, confidence, extractor and version, snippet hash) and the file's outgoing and incoming links.
- **FR-011**: Every snapshot, whatever its size, MUST open in the graph at the System level with components
  collapsed. The overview MUST show components sized by dependents, with
  bundled links between components, cycle links in red and hotspots marked; a component MUST expand on click and a
  minimap MUST show the position in the whole graph. The current view MUST be exportable as an image.

**Import (US2)**

- **FR-012**: Import MUST accept a public GitHub URL with an optional ref and a ZIP upload, start an analysis job,
  show its stage until done or failed, show the pinned commit, the safety limits and, when done, the language
  coverage, and open the new snapshot on request.
- **FR-013**: A failed job MUST show its failure reason; a reused analysis MUST open without waiting.

**Insights (US3)**

- **FR-014**: Cycles MUST list every cycle group with files, link count, type-only mark and an example cycle, and for
  the selected group the suggested links to remove with file, line, line text and method, labelled "recommendation
  only".
- **FR-015**: Hotspots MUST show a map with tile size = lines of code and colour = score, a top-risk table (file,
  commits, transitive dependents, bus factor), the history base, and "history not available" with the reason when
  there is no history. No author names or e-mails are shown.
- **FR-016**: Search MUST find files by path and symbols by exact name and open the result in the graph.

**Agents (US4)**

- **FR-017**: Ask agents MUST send a question about the open snapshot, show the streamed steps live, then the answer
  with verified facts and their citations, cycle warnings and hypotheses in distinct styles, run statistics (tool
  calls, time, model) and a small graph of the cited files linked to the main graph; suggested questions MAY be
  offered as fixed text.
- **FR-018**: Agent trace MUST show, for the selected answer of the history, each step with role, tool, arguments,
  result summary and duration, the revisions, the claims with their status, and the budget used out of the limit.
- **FR-018a**: The UI MUST keep the last 20 finished answers with their traces per snapshot in the user's browser, so
  they survive a page reload; older ones are dropped first, a "clear history" action removes them, and nothing is
  sent to or stored on the server. Kept answers are shown exactly like fresh ones (as text, facts and hypotheses
  distinct).

**Integrations and placeholders (US6)**

- **FR-019**: MCP for agents MUST show copyable connection settings for Claude Code and Cursor for the open snapshot
  and the list of tools the MCP server exposes, with their read-only nature.
- **FR-020**: PR impact and Security MUST open a page stating they are not available in this version, with no sample
  data.

**Backend additions (computed by code, available to UI, CLI and MCP alike)**

- **FR-021**: The graph query layer MUST provide components of a snapshot: a partition of its files by community
  detection with a fixed seed and stable tie-break (constitution II), each component named after the longest common
  folder of its files, or, when they share none, the most frequent top-level folder among them (ties by path order);
  equal names are made unique with ` · 2`, ` · 3`, … in the order of each component's first file path. Each
  component has its files, file count, links to other components with their import counts and
  confidence, and whether it contains a cycle. It MUST be available through
  the command line, the MCP server and the HTTP API, with byte-identical answers.
- **FR-022**: The cycles answer MUST include, for each cycle group, the suggested links to remove: a minimum
  feedback arc set (the fewest links whose removal leaves the group without cycles), computed exactly for groups of
  up to 20 files, with ties broken by the fewest imported names in total and then by path order; for larger groups the
  greedy rule (repeatedly the link that breaks the most remaining cycles, then the fewest imported names, then path
  order). A group of up to 20 files whose exact search exceeds a fixed work budget also uses the greedy rule. Each suggested link carries its import line(s), and the answer states the method (`exact` or `greedy`). It
  MUST be available through all interfaces like FR-021.
- **FR-023**: The service MUST provide per-file line counts of a stored snapshot in one request, so that the hotspot
  map and component sizes (the sum of their files' line counts) do not need one request per file.
- **FR-024**: The service MUST tell the UI which model answers questions and whether asking is enabled, so the header
  badge and Ask agents can show it.
- **FR-025**: When a built UI is present, the Graphora service MUST serve it from the same address as the API, so that
  starting the service and opening its address shows the UI; without a build the API works as before. The built UI is
  static files only: serving it runs no code from analyzed repositories and adds no write endpoints.

### Key Entities

- **Snapshot view**: repository, snapshot (commit), current screen, view level, selected file or component, filters.
- **Component**: a named group of files of one snapshot, with file count, lines of code, links to other components
  and a cycle mark.
- **Cycle group**: files that import each other in a loop, an example cycle, a type-only mark, and the suggested links
  to remove with the method used (`exact` for groups of up to 20 files, `greedy` above).
- **Import job**: source (GitHub URL and ref, or ZIP), stage, pinned commit, result snapshot or failure reason.
- **Agent run**: question, streamed steps, final answer (facts with citations, hypotheses), claims with statuses,
  budget used; the last 20 finished runs per snapshot are kept in the browser.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can go from an empty screen to the impact of a chosen file of an imported fixture repository
  in under 2 minutes without reading documentation.
- **SC-002**: On every fixture repository, 100% of the files, links, impact sets, cycles, hotspots and definitions
  shown by the UI equal the service answers for the same snapshot (no fact is computed or invented by the UI).
- **SC-003**: A snapshot of 5,000 files opens to its overview in under 5 seconds, and expanding a component or
  toggling impact mode responds in under 1 second on a typical developer laptop.
- **SC-004**: 0 of the hostile inputs in the test suite (markup or script in file contents, paths, symbol names,
  agent answers, repository names) are rendered as anything but text.
- **SC-005**: Every screen of `docs/demo` § 1–9 and § 12 is reachable from the sidebar and shows real data from a
  stored snapshot; § 10 and § 11 show "not available in this version" with no data.
- **SC-006**: Every error state of the service (not found, stale, busy, model unavailable, store unavailable, job
  failure kinds) has a visible message and next step in the test suite.
- **SC-007**: Component and cut-suggestion answers are byte-identical across two runs and across the command line,
  MCP and HTTP for every fixture.
- **SC-008**: All tests that existed before this feature pass unchanged.
- **SC-009**: With a built UI present, starting the service with one command and opening its address shows the
  working UI with no other process running.

## Assumptions

- One user at a time on a local machine (`graphora serve` on localhost); no accounts, authentication, sharing or
  deployment in this feature. During UI development a dev server forwards API calls to the service; otherwise the
  service itself serves the built UI (FR-025). Both use one address, so no cross-origin setup is needed.
- Dark theme only, as in the mockups; English interface; current desktop Chrome, Firefox and Safari; no mobile
  layout.
- The mockups set layout, colours, typography and interaction style; the numbers, file names, "named by agent"
  component names, author handles in the hotspot table and the 90-day window in `07-hotspots.png` are illustrative.
  Real values follow the backend: component names come from folders, bus factor is a number, the history window is
  the 12 months of feature 014.
- The "Analyst · evidence" explanation cards next to Cycles and Hotspots in the mockups are replaced by an "Ask agents
  about this" action that opens Ask agents with a prepared question; the UI does not generate explanations itself.
- The "Symbol" view level of the mockups is covered by symbol search and the definitions of the selected file; a
  separate symbol-level graph is out of scope.
- The MCP page lists the tool names the MCP server actually exposes (feature 006 and later), not the illustrative
  names of `10-mcp.png`; the "tool calls vs grep" and "context tokens" cards are benchmark targets (feature 016) and
  are not shown as measured results.
- Job progress is shown by stage as the service reports it; the per-step timings and percentages of `01-import.png`
  are shown only where the service provides them.
- The agent trace shows token counts and durations only when the streamed events carry them.
- Agent-named components, PR impact, security analysis, light theme and authentication are later features.
- Large-graph rendering may switch to a faster renderer if the default one cannot meet SC-003 (constitution:
  technical constraints).
