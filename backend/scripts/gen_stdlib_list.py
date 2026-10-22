"""Regenerate src/graphora/resolve/data/stdlib_modules.txt.

Runs only the local interpreters named on the command line, never analyzed code:

    uv run python scripts/gen_stdlib_list.py 3.12 3.13 3.14 > src/graphora/resolve/data/stdlib_modules.txt

Bump STDLIB_VERSION in graphora.resolve.python when the list changes.
"""

import subprocess
import sys

VERSION_TAG = "python-stdlib@3.14.0"


def names_for(version: str) -> set[str]:
    code = "import sys; print('\\n'.join(sorted(sys.stdlib_module_names)))"
    out = subprocess.run(
        ["uv", "run", "--no-project", "--python", version, "python", "-I", "-c", code],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return set(out.split())


def main(versions: list[str]) -> None:
    names = {"__future__"}
    for version in versions:
        names |= names_for(version)
    print(f"# {VERSION_TAG} (union of CPython {', '.join(versions)})")
    for name in sorted(names):
        print(name)


if __name__ == "__main__":
    main(sys.argv[1:] or ["3.12", "3.13", "3.14"])
