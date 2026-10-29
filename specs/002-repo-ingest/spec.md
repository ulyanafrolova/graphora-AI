# Feature Specification: Repository Ingest from GitHub and ZIP

**Feature Branch**: `002-repo-ingest`

**Created**: 2026-10-28

**Status**: Draft

**Input**: User description: "002 repo-ingest: load a repository for analysis from a GitHub link or a ZIP archive.
GitHub: URL (owner/repo, optionally branch/tag/commit) → one GitHub API request without a token to learn the SHA →
download the tarball of that SHA. ZIP: the user provides an archive file. Safe extraction: no absolute paths and no
`..`, no symlink/hardlink pointing outside, a limit on the extracted size (zip bomb), a limit on the number of files;
archive contents are data, nothing is executed. Extraction into a temporary folder, cleaned up even on error.
Result: fetch_snapshot(source) → (root, repository, snapshot_id), then build() is called; for GitHub snapshot_id = the
commit SHA, for ZIP — content:<hash>. The change in build() (Ulyana's module, graph/build.py) is made in the same PR:
an optional snapshot parameter — if given, it is used, otherwise the snapshot is computed as today. The behaviour of
analyze for a local folder does not change, all existing tests stay green. Ulyana reviews and approves this change as
the module owner. Tests without network access."

## Clarifications

### Session 2026-10-28

- Q: How does `analyze` tell a folder, a GitHub link and a ZIP file apart, and how is the ref given separately from
  the link? → A: One positional argument, detected automatically: starts with `https://` → GitHub link; an existing
  folder → local analysis; an existing file → ZIP, checked by its content, not by its extension. The ref is given with
  a `--ref` option, allowed only with a link.
- Q: Which failure group (exit status) covers "repository or ref not found / private" and "GitHub rate limit used
  up"? → A: Not found, private or unknown ref is bad input (the existing usage status); the rate limit is a
  remote/network failure, which may succeed on retry.
- Q: Do downloading and extracting count against the run's time limit (300 s today), or only the analysis? → A: One
  time limit covers the whole run: ref resolution, download, extraction and analysis. Crossing it is a limit error,
  with cleanup.
- Q: Are hardlink entries in an archive skipped under the existing `symlink` reason, or is the whole archive
  rejected? → A: The whole archive is rejected as unsafe, naming the entry; symlinks are still skipped as `symlink`.
  No graph schema change.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analyze a public GitHub repository by its link (Priority: P1)

A developer has a link to a public GitHub repository and wants its dependency graph without cloning it by hand. They
give the link to Graphora, optionally with a branch, tag or commit. Graphora finds out which exact commit that is,
downloads exactly that commit, analyzes it and returns the same graph file as for a local folder. Every edge in the
graph is pinned to the real commit SHA, not to a content hash.

**Why this priority**: Analysis "by link" is the main entry point of the product (import screen, API, pipeline 007).
A commit-pinned snapshot id is what makes `file:line@commit` provenance real for remote repositories.

**Independent Test**: With the network replaced by recorded responses, give a GitHub link of a fixture repository and
check that the graph equals the graph of the same fixture analyzed as a local clean clone at the same commit.

**Acceptance Scenarios**:

1. **Given** a link `https://github.com/owner/repo` with no ref, **When** the developer runs the analysis, **Then**
   Graphora resolves the repository's default branch to a commit SHA, analyzes that commit, and every edge's snapshot
   id equals that SHA.
2. **Given** a link with a branch, tag or full commit SHA, **When** analyzed, **Then** exactly that ref is resolved to
   one commit SHA and that commit is analyzed.
3. **Given** the same link and ref analyzed twice while the branch has not moved, **When** both outputs are compared,
   **Then** they are byte-identical.
4. **Given** a repository that does not exist, is private, or a ref that does not exist, **When** analyzed, **Then**
   the analysis stops with a clear message naming the repository or ref, and no graph is written.
5. **Given** GitHub refuses the request because the anonymous rate limit is used up, **When** analyzed, **Then** the
   message says so and when it can be retried, if GitHub reports it.

---

### User Story 2 - Analyze a project uploaded as a ZIP archive (Priority: P2)

A developer has a project as a ZIP file (for example, GitHub's "Download ZIP", or a project that is not on GitHub).
They give the file to Graphora and receive the graph of its contents.

**Why this priority**: It covers private and non-GitHub code without any credentials, and it is the upload path for
the later web UI. It depends on the same safe extraction as Story 1, so it comes second.

**Independent Test**: Build a ZIP of a fixture repository inside the test, analyze it, and compare the graph with the
fixture's `expected.json` except for the snapshot id, which is `content:<hash>`.

**Acceptance Scenarios**:

1. **Given** a ZIP whose files sit under one top-level folder (as GitHub's "Download ZIP" produces), **When**
   analyzed, **Then** paths in the graph are relative to that folder, exactly as if the folder were analyzed locally.
2. **Given** a ZIP with files at its top level, **When** analyzed, **Then** paths are relative to the archive root.
3. **Given** the same ZIP analyzed twice, **When** outputs are compared, **Then** they are byte-identical, and the
   snapshot id is `content:<hash>` of the included files.
4. **Given** a file that is not a valid ZIP archive, **When** analyzed, **Then** the analysis stops with a clear
   message and no graph is written.

---

### User Story 3 - Hostile archives cannot harm the machine (Priority: P1)

Graphora runs on untrusted public repositories and uploads. Whatever an archive contains, extraction never writes
outside its temporary folder, never fills the disk, never runs anything, and always cleans up after itself.

**Why this priority**: This is a non-negotiable constitution rule (Principle I). It ships together with Story 1, since
every GitHub tarball is extracted the same way.

**Independent Test**: Build hostile archives inside the tests (path traversal, absolute paths, symlinks and hardlinks
pointing outside, a highly compressed bomb, too many entries) and check that each one is handled as described below,
that nothing appears outside the temporary folder, and that the temporary folder is gone afterwards.

**Acceptance Scenarios**:

1. **Given** an archive entry with an absolute path or a path containing `..`, **When** extracted, **Then** the whole
   archive is rejected with a message naming the entry, and no file is written anywhere outside the temporary folder.
2. **Given** an archive with a symlink entry, **When** extracted, **Then** no link is created on disk; the entry is
   listed among skipped paths in the coverage report with reason `symlink`, the same way local symlinks are reported
   today.
3. **Given** an archive with a hardlink entry, **When** extracted, **Then** the whole archive is rejected as unsafe
   with a message naming the entry, and nothing is left on disk.
4. **Given** an archive whose extracted size or entry count would exceed the limits, **When** extracted, **Then**
   extraction stops as soon as the limit is crossed (not after writing everything), the result is a limit error, and
   the temporary folder is removed.
5. **Given** any failure (network error, invalid archive, limit, interruption by the user), **When** the run ends,
   **Then** no temporary files or folders created by the run remain.
6. **Given** an archive containing scripts, build files or executable bits, **When** analyzed, **Then** nothing from
   the archive is run, and extracted files are never marked executable.

---

### User Story 4 - Local folder analysis keeps working unchanged (Priority: P1)

Developers who already run `graphora analyze <dir>` see no difference: same arguments, same output, same exit codes.

**Why this priority**: The change to graph building touches another owner's module. It must be provably safe.

**Independent Test**: The full existing test suite passes without changes to existing tests or to any
`expected.json`.

**Acceptance Scenarios**:

1. **Given** any existing fixture, **When** analyzed as a local folder, **Then** the output is byte-identical to the
   output before this feature.
2. **Given** graph building is asked to use a snapshot id supplied by the caller, **When** it builds, **Then** every
   edge and the document carry exactly that id, and nothing else in the output changes.

---

### Edge Cases

- A link in another accepted form: with a trailing `.git`, a trailing slash, or `/tree/<ref>`. Links to other hosts,
  to a single file (`/blob/...`), or with extra path segments are rejected with a message listing accepted forms.
- A ref name containing `/` (e.g. `feature/x`) in a `/tree/` link is ambiguous; the developer can pass the ref
  with `--ref`, and that is what the error message suggests.
- An existing file that does not start with a ZIP signature (whatever its extension), and a path that does not
  exist and does not start with `https://`, are reported as bad input, as a file or missing path is today. A file
  that starts with a ZIP signature but cannot be read as ZIP is reported as an invalid archive.
- A `/tree/<ref>` link given together with `--ref` is bad input, even if both name the same ref.
- A repository with no commits (empty) is reported as such; no graph is written.
- A short commit SHA is accepted only if GitHub resolves it to exactly one commit.
- The archive download is larger than allowed: the download stops at the limit, as a limit error.
- Git submodules are not fetched (GitHub tarballs do not contain them); their folders are empty or absent and are
  not analyzed.
- Files that are Git LFS pointers are analyzed as the small text files they are; LFS content is not fetched.
- A repository whose `.gitattributes` uses `export-ignore` or `export-subst` is analyzed as GitHub's archive of
  the commit serves it, which can differ from a clone in the files listed there. FR-016 applies to repositories
  that do not use these attributes.
- Two archive entries map to the same path (duplicates, or names that differ only by letter case or Unicode
  normalisation): the archive is rejected rather than one file silently replacing the other. This applies on every
  system, not only on case-insensitive disks, so the result does not depend on the machine.
- File names that are not valid UTF-8, or contain characters forbidden on the current system: the archive is rejected
  with a message naming the entry.
- Directory entries, empty folders and file permission bits in the archive do not affect the graph.
- The network drops during the download: a clear network error, no graph, cleanup done.
- The `--out` path can never be inside the temporary folder (it is outside by construction).

## Requirements *(mandatory)*

### Functional Requirements

**Sources**

- **FR-001**: The analysis command MUST accept, in the same single positional argument that takes a local folder
  today, either a public GitHub repository link or a path to a ZIP file. The kind of source is detected
  automatically: an argument starting with `https://` is a link; an existing folder is a local folder; an existing
  file is a ZIP archive, recognised by its content, not by its file extension. A local folder keeps working exactly
  as before.
- **FR-002**: For a GitHub link the system MUST accept `https://github.com/<owner>/<repo>` with an optional `.git`
  suffix, optional trailing slash and optional `/tree/<ref>`. The ref MAY instead be given with a `--ref` option;
  `--ref` with a local folder or a ZIP file is rejected as bad input. Anything else is rejected with a message listing
  accepted forms.
- **FR-003**: For a GitHub link the system MUST resolve the ref (or the default branch) to one full commit SHA with a
  single anonymous request, then download the archive of exactly that SHA, not of the branch name, so that the
  analyzed content cannot differ from the resolved commit.
- **FR-004**: The system MUST NOT require or send any GitHub credentials in this feature.
- **FR-005**: Each fetched source MUST be identified by a repository name (`github.com/<owner>/<repo>` for GitHub;
  the archive file name without extension for ZIP) and a snapshot id: the full commit SHA for GitHub,
  `content:<hash>` for ZIP, computed the same way as for local folders that are not git working trees.

**Safe extraction**

- **FR-006**: Archives MUST be extracted only into a new, empty temporary folder created for this run.
- **FR-007**: The system MUST reject the whole archive if any entry has an absolute path, a drive letter, a `..`
  segment, or would otherwise resolve outside the temporary folder.
- **FR-008**: Symlink entries MUST NOT be created on disk. They MUST appear among skipped paths in the coverage report
  with the existing reason `symlink`. Hardlink entries MUST NOT be created either: an archive containing any hardlink
  entry MUST be rejected as a whole as an unsafe archive, with a message naming the entry.
- **FR-009**: The system MUST enforce, during extraction, limits on the total extracted size and the number of
  entries, and on the downloaded archive size. Crossing a limit MUST stop the work immediately and end with the same
  kind of limit error the local analysis uses. Limits MUST be adjustable by the caller and have safe defaults.
- **FR-009a**: The existing run time limit MUST cover the whole run: resolving the ref, downloading, extracting and
  analyzing share one deadline that starts when the run starts. A stalled or slow download that crosses it ends with
  the limit error, and the temporary folder is removed.
- **FR-010**: Extracted files MUST be written as plain, non-executable files. Nothing from the archive is run,
  imported, built or installed (Principle I).
- **FR-011**: The temporary folder and everything in it MUST be removed when the run ends, whether it succeeds,
  fails, or is interrupted.
- **FR-012**: After extraction, the folder MUST go through the same walk, exclusion rules and limits as a local
  folder; no extra rules apply to fetched content and none are skipped.
- **FR-013**: When an archive's entries all sit under one top-level folder and nothing else, that folder MUST be used
  as the project root.

**Graph building**

- **FR-014**: Graph building MUST accept an optional snapshot id from its caller. When given, it is used for the
  document and every edge; when not given, the snapshot id is computed exactly as today.
- **FR-015**: For a local folder the output MUST be byte-identical to the output before this feature.
- **FR-016**: The graph of a GitHub commit MUST be byte-identical to the graph of a clean local clone of the same
  commit (same files, same paths, same snapshot id), unless the repository uses `export-ignore` or `export-subst`
  (see Edge Cases).

**Errors and output**

- **FR-017**: Each failure MUST produce a one-line message saying what went wrong and with what (link, ref, entry
  name, or limit), and a distinct exit status for: bad input, limit exceeded, unsafe or invalid archive, and
  remote/network failure. Existing exit statuses keep their meaning: bad input reuses the existing usage status and
  limit exceeded reuses the existing limit status. A repository or ref that does not exist or is private, and an
  empty repository, are bad input. The anonymous rate limit being used up, a dropped connection and any other
  GitHub-side error are remote/network failures, the only group a caller may retry unchanged.
- **FR-018**: No graph file is written on any failure; an existing output file is left untouched.

**Tests**

- **FR-019**: The automated test suite MUST run without network access. Remote behaviour is tested with recorded or
  synthetic responses, and archives (including hostile ones) are built by the tests themselves.

### Key Entities

- **Source**: what the user asked to analyze: a local folder, a GitHub link with an optional ref, or a ZIP file.
- **Fetched snapshot**: the result of fetching a source: a temporary project root on disk, the repository name and
  the snapshot id. It exists only for the duration of one run.
- **Ingest limits**: maximum download size, maximum extracted size, maximum number of entries; plus the existing
  file and byte limits of the walk, and the existing time limit, which covers the whole run including fetching.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer gets the graph of a public GitHub repository with one command and a link, without cloning
  it or creating any account or token.
- **SC-002**: For every fixture repository, the graph obtained through a GitHub link (with recorded responses) and
  through a ZIP of the same files equals the local-folder graph, apart from the snapshot id for ZIP.
- **SC-003**: 100% of the hostile archive cases in User Story 3 are handled as specified, and in none of them does a
  file appear outside the temporary folder.
- **SC-004**: After every test run, including failing and interrupted cases, zero temporary files or folders created
  by Graphora remain.
- **SC-005**: A zip bomb that would expand to more than 100× the extracted size limit is stopped having written no
  more than the limit plus one buffer.
- **SC-006**: All tests that existed before this feature pass unchanged, and the full suite passes with the network
  disabled.
- **SC-007**: A repository of up to the default limits (5000 files, 50 MB of analyzed content) is fetched and
  analyzed within the existing 300-second time limit on a normal home connection. A test with a download that never
  finishes ends with the limit error once a short caller-set time limit is crossed, and leaves no temporary files.

## Assumptions

- Only public GitHub repositories on github.com are in scope. Private repositories, tokens, GitHub Enterprise,
  GitLab and Bitbucket are out of scope for this slice.
- The anonymous GitHub limit (about 60 requests per hour per address) is acceptable; each analysis uses one API
  request plus one archive download.
- Only ZIP is accepted as an uploaded archive in this slice; `.tar.gz` is used internally for GitHub but not offered
  as an upload format.
- The entry point is the existing `analyze` command. HTTP upload, the API and storage come in features 005 and 007,
  which will call the same fetch step.
- Default limits (download size, extracted size, entry count) are chosen in the plan; they are at least as large as
  the existing walk limits so that a repository that passes the walk is not rejected earlier.
- The "symlink" skip reason already in the graph schema is reused for archive symlinks. Hardlinks are rejected, not
  skipped, so this feature needs no change to the graph schema. GitHub tarballs and ZIP files from normal tools do
  not contain hardlinks, so a hardlink entry indicates a crafted archive.
- The change to graph building is made in this PR and reviewed and approved by Ulyana as owner of `graph/build.py`.
- Analyzing a fetched snapshot is the same as analyzing a folder: no special-casing in detection, adapters or
  resolvers.
