"""Commits and trees of a GitHub commit's history over git's read-only smart HTTP, no file contents and no git
binary (specs/014-hotspots research § R5)."""

from __future__ import annotations

from pathlib import Path

import urllib3
from dulwich.client import Urllib3HttpGitClient
from dulwich.repo import Repo

from graphora.graph.model import HistoryReason
from graphora.history.reader import WINDOW_SECONDS
from graphora.ingest.github import USER_AGENT
from graphora.ingest.source import GitHubSource
from graphora.ingest.walk import Deadline

MARGIN_SECONDS = 30 * 86400  # boundary commits of the window keep their parents


class _Stop(Exception):
    def __init__(self, reason: HistoryReason) -> None:
        super().__init__(reason)
        self.reason = reason


def _remote_url(source: GitHubSource) -> str:
    """Replaced by a local server in tests."""
    return f"https://github.com/{source.owner}/{source.repo}.git"


def _fetch(url: str, repo: Repo, sha: bytes, budget: list[int], deadline: Deadline, **options) -> frozenset[bytes]:
    """One `fetch_pack` into `repo`; returns the commits whose parents were not sent."""
    if deadline.remaining() <= 0:
        raise _Stop("time_limit")
    pool = urllib3.PoolManager(
        headers={"User-Agent": USER_AGENT},
        retries=urllib3.Retry(total=0, redirect=0, raise_on_redirect=True),
        timeout=urllib3.Timeout(total=deadline.remaining()),
    )
    client = Urllib3HttpGitClient(url, pool_manager=pool)
    pack, commit, abort = repo.object_store.add_pack()

    def write(data: bytes) -> None:
        budget[0] -= len(data)
        if budget[0] < 0:
            raise _Stop("too_large")
        if deadline.remaining() <= 0:
            raise _Stop("time_limit")
        pack.write(data)

    try:
        result = client.fetch_pack(
            "", lambda refs, depth=None: [sha], repo.get_graph_walker(), write, filter_spec=b"blob:none", **options
        )
    except BaseException:
        abort()
        raise
    commit()
    return frozenset(result.new_shallow or ())


def fetch_history(
    source: GitHubSource, sha: str, workdir: Path, max_bytes: int, deadline: Deadline
) -> tuple[Repo, frozenset[bytes]] | HistoryReason:
    """A bare repository with the window's commits and trees plus its shallow commits, or why not. A server without
    `deepen-since` sends the whole history: bigger, never wrong, since the reader applies the window."""
    url = _remote_url(source)
    budget = [max_bytes]
    workdir.mkdir(parents=True, exist_ok=True)
    head = Repo.init_bare(str(workdir / "head.git"), mkdir=True)
    try:
        _fetch(url, head, sha.encode(), budget, deadline, depth=1)
        since = head[sha.encode()].commit_time - WINDOW_SECONDS - MARGIN_SECONDS
    except _Stop as stop:
        return stop.reason
    except Exception:
        return "fetch_failed"
    finally:
        head.close()

    repo = Repo.init_bare(str(workdir / "history.git"), mkdir=True)
    try:
        try:
            shallow = _fetch(url, repo, sha.encode(), budget, deadline, shallow_since=str(since))
        except _Stop:
            raise
        except Exception:
            shallow = _fetch(url, repo, sha.encode(), budget, deadline)
        repo[sha.encode()]
    except _Stop as stop:
        repo.close()
        return stop.reason
    except Exception:
        repo.close()
        return "fetch_failed"
    return repo, shallow
