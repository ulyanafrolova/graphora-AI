"""Regenerate src/graphora/resolve/data/node_builtins.txt (research.md § R6 of 003-ts-js-analysis).

Needs a local Node.js. Runs only `node -p` to print `module.builtinModules`, never analyzed code, and is
never run by tests or by `graphora analyze`. Names already in the file are kept, so the list stays the union
over every Node version it was generated with:

    uv run python scripts/gen_node_builtins.py

Bump BUILTINS_VERSION in graphora.resolve.js and VERSION_TAG below when the list changes.
"""

import subprocess
from pathlib import Path

VERSION_TAG = "node-builtins@26.0.0"
LIST = Path(__file__).resolve().parents[1] / "src" / "graphora" / "resolve" / "data" / "node_builtins.txt"


def local_names() -> set[str]:
    out = subprocess.run(
        ["node", "-p", "require('module').builtinModules.join('\\n')"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return set(out.split())


def normalize(names: set[str]) -> tuple[list[str], list[str]]:
    """Top-level bare names, and prefix-only `node:` names kept whole."""
    bare = {n.split("/")[0] for n in names if not n.startswith("node:")}
    prefixed = {n for n in names if n.startswith("node:")}
    return sorted(bare), sorted(prefixed)


def main() -> None:
    existing = {line for line in LIST.read_text(encoding="utf-8").split("\n") if line and not line.startswith("#")}
    bare, prefixed = normalize(existing | local_names())
    LIST.write_text("\n".join([f"# {VERSION_TAG}", *bare, *prefixed]) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
