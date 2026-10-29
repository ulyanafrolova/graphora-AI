"""What the user asked to analyze (specs/002-repo-ingest/research.md § R4, data-model.md § Source)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from graphora.ingest.errors import BadInput

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_OWNER = re.compile(r"^[A-Za-z0-9-]{1,39}$")
_REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_REF_FORBIDDEN = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]|\.\.|@\{|//")
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06")  # first entry, or the end record of an empty archive


@dataclass(frozen=True)
class LocalSource:
    path: Path


@dataclass(frozen=True)
class GitHubSource:
    owner: str
    repo: str
    ref: str | None


@dataclass(frozen=True)
class ZipSource:
    path: Path


Source = LocalSource | GitHubSource | ZipSource


def _check_ref(ref: str) -> str:
    """git's ref-name rules (research § R2); a bad ref never reaches GitHub."""
    parts = ref.split("/")
    if (
        not ref
        or _REF_FORBIDDEN.search(ref)
        or ref.startswith(("-", "/"))
        or ref.endswith(("/", ".lock", "."))
        or ref == "@"
        or any(p.startswith(".") for p in parts)
    ):
        raise BadInput(f"invalid ref name: {ref}")
    return ref


def _parse_link(argument: str, ref: str | None) -> GitHubSource:
    bad = BadInput(
        f"not a GitHub repository link: {argument} "
        "(accepted: https://github.com/<owner>/<repo>[.git][/] or .../tree/<ref>)"
    )
    parsed = urlsplit(argument)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or "?" in argument or "#" in argument:
        raise bad
    parts = parsed.path.split("/")[1:]
    link_ref = None
    if len(parts) >= 3 and parts[2] == "tree":
        tree = parts[3:]
        if not tree or tree == [""]:
            raise bad
        if len(tree) > 1:
            raise BadInput(f'ref "{"/".join(tree)}" in /tree/ has several segments; pass it with --ref')
        link_ref = tree[0]
    elif not (len(parts) == 2 or (len(parts) == 3 and parts[2] == "")):
        raise bad
    owner, repo = parts[0], parts[1]
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    if not _OWNER.match(owner) or not _REPO.match(repo) or repo in (".", ".."):
        raise bad
    if link_ref is not None and ref is not None:
        raise BadInput("--ref given twice: in the link and as --ref")
    final_ref = link_ref if link_ref is not None else ref
    return GitHubSource(owner.lower(), repo.lower(), _check_ref(final_ref) if final_ref is not None else None)


def parse_source(argument: str, ref: str | None) -> Source:
    if _SCHEME.match(argument):
        return _parse_link(argument, ref)
    path = Path(argument)
    if path.is_dir():
        if ref is not None:
            raise BadInput("--ref is allowed only with a GitHub link")
        return LocalSource(path)
    if path.is_file() and _starts_with_zip_signature(path):
        if ref is not None:
            raise BadInput("--ref is allowed only with a GitHub link")
        return ZipSource(path)
    raise BadInput(f"not a directory or ZIP archive: {argument}")


def _starts_with_zip_signature(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(4) in _ZIP_SIGNATURES
    except OSError:
        return False
