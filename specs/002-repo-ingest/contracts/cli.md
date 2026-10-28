# CLI Contract: `graphora analyze` (changes in 002)

Base contract: [001 contracts/cli.md](../../001-python-graph-cli/contracts/cli.md), as changed by
[003 contracts/cli.md](../../003-ts-js-analysis/contracts/cli.md). This file lists only what 002 changes.

```
graphora analyze <source> [--ref <ref>] [--out <file>]
                 [--max-files N] [--max-bytes N] [--max-seconds N]
                 [--max-archive-bytes N] [--max-extract-bytes N] [--max-entries N]
```

| Argument | Default | Meaning |
|---|---|---|
| `<source>` | required | A local folder (unchanged), a GitHub link, or a ZIP file. Detection: [research R4](../research.md) |
| `--ref <ref>` | default branch | Branch, tag or commit SHA. Only with a link that has no `/tree/` part |
| `--max-seconds N` | `300` | Now covers the whole run: resolving, downloading, extracting and analyzing |
| `--max-archive-bytes N` | `209715200` | Maximum compressed download size, or ZIP file size |
| `--max-extract-bytes N` | `209715200` | Maximum bytes written while extracting |
| `--max-entries N` | `20000` | Maximum files and folders created while extracting |

Accepted link forms: [data-model.md § GitHub link rules](../data-model.md).

## Behaviour changes

- **Local folder.** Unchanged in arguments, output and exit statuses. The only visible difference: a missing
  path or a file that is not a ZIP now says `not a directory or ZIP archive: <arg>` (still status `2`).
  `--ref` with a folder is a usage error.
- **GitHub link.** One anonymous API request resolves the ref to a commit SHA, then the archive of that SHA
  is downloaded. No credentials are read or sent. The document's `snapshot` and every edge's snapshot is
  the 40-character SHA. An extra info line is printed before the summary:
  `graphora: info: fetched github.com/<owner>/<repo> at <sha>`.
- **ZIP file.** Extracted and analyzed; `snapshot` is `content:<hash>` of the analyzed files. Info line:
  `graphora: info: extracted <name>.zip`.
- **Coverage.** Symlinks found in an archive appear in `skipped` with reason `symlink`, as local symlinks
  do. No new skip reason; the schema is unchanged.
- **`--out`.** Must not be inside a local `<source>` folder (unchanged). For a link or ZIP it is outside
  the temp folder by construction. Written only after the temp folder is removed.
- **Temp files.** One `graphora-*` folder in the system temp folder per run, removed on success, error and
  interruption (`SIGINT`, `SIGTERM`).

## Exit codes

| Code | When |
|---|---|
| `0` | A graph was produced (unchanged) |
| `2` | Bad input (unchanged meaning, wider use): bad argument, bad link or ref, `--ref` misuse, repository not found or private, ref not found or ambiguous, empty repository, output cannot be written |
| `3` | A limit was exceeded (unchanged meaning): walk limits, the run deadline, or one of the three new limits |
| `4` | **New.** Unsafe or invalid archive. The message names the entry, or says why the archive cannot be read |
| `5` | **New.** Remote or network failure: rate limit, connection error, unexpected GitHub response. The only status worth retrying unchanged |
| `130` | **New.** Interrupted by `SIGINT` or `SIGTERM`; temp files removed |

## New messages (stderr, one line each)

```
graphora: error: not a directory or ZIP archive: <arg>
graphora: error: not a GitHub repository link: <arg> (accepted: https://github.com/<owner>/<repo>[.git][/] or .../tree/<ref>)
graphora: error: ref "<ref>" in /tree/ has several segments; pass it with --ref
graphora: error: --ref is allowed only with a GitHub link
graphora: error: --ref given twice: in the link and as --ref
graphora: error: invalid ref name: <ref>
graphora: error: repository not found or private: github.com/<owner>/<repo>
graphora: error: ref not found or ambiguous in github.com/<owner>/<repo>: <ref>
graphora: error: repository is empty: github.com/<owner>/<repo>
graphora: error: GitHub API rate limit reached; retry after <YYYY-MM-DD HH:MM> UTC
graphora: error: GitHub request failed: <host> <status or reason>
graphora: error: archive size limit exceeded: at least <n> bytes > --max-archive-bytes <v>
graphora: error: extracted size limit exceeded: at least <n> bytes > --max-extract-bytes <v>
graphora: error: entry limit exceeded: at least <n> entries > --max-entries <v>
graphora: error: unsafe archive entry <name>: <path outside the folder | hardlink | device | duplicate of <other> | ...>
graphora: error: invalid ZIP archive <file>: <reason>
graphora: error: interrupted
```

The rate-limit line omits the `retry after` part if GitHub sends no reset time. Wording may be refined in
implementation; tests assert the status, the named object (link, ref, entry, limit) and a stable key
phrase.

## Examples

```
$ graphora analyze https://github.com/owner/repo/tree/v1.2.0 --out /tmp/repo.json
graphora: info: fetched github.com/owner/repo at 3f9c…
graphora: info: analyzed 61 files, 410 edges (12 unresolved), snapshot 3f9c…

$ graphora analyze https://github.com/owner/repo --ref feature/x

$ graphora analyze ./project.zip
graphora: info: extracted project.zip
graphora: info: analyzed 42 files, 97 edges (3 unresolved), snapshot content:…

$ graphora analyze ./evil.zip; echo $?
graphora: error: unsafe archive entry ../../etc/passwd: path outside the folder
4
```

Counts and SHAs are illustrative.
