"""Regenerate src/graphora/resolve/data/dotnet_namespaces.txt and dotnet_types.txt (specs/007-csharp-analysis
research.md § R6, specs/008-csharp-type-references research.md § R3).

Needs network access to api.nuget.org. Downloads the reference packs of the .NET shared frameworks, opens each
`.nupkg` as ZIP data in memory and reads type names from the XML documentation files (`T:Namespace.Type`).
Never runs .NET, never executes anything from the packages, and is never run by tests or `graphora analyze`:

    uv run python scripts/gen_dotnet_namespaces.py

Bump NAMESPACES_VERSION / TYPES_VERSION in graphora.resolve.csharp and VERSION below when a list changes.
"""

import io
import urllib.request
import zipfile
from pathlib import Path
from xml.parsers import expat

VERSION = "10.0.0"
TFM = "net10.0"
FRAMEWORKS = ("Microsoft.AspNetCore.App", "Microsoft.NETCore.App", "Microsoft.WindowsDesktop.App")
DATA = Path(__file__).resolve().parents[1] / "src" / "graphora" / "resolve" / "data"
LIST = DATA / "dotnet_namespaces.txt"
TYPES = DATA / "dotnet_types.txt"
FEED = "https://api.nuget.org/v3-flatcontainer"


def _download(package: str) -> bytes:
    url = f"{FEED}/{package.lower()}/{VERSION}/{package.lower()}.{VERSION}.nupkg"
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 (fixed https URL)
        return response.read()


def _refuse_doctype(*_args: object) -> None:
    raise ValueError("DOCTYPE not allowed")


def _type_names(xml: bytes) -> set[str]:
    names: set[str] = set()
    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = _refuse_doctype

    def start(tag: str, attrs: dict[str, str]) -> None:
        member = attrs.get("name", "")
        if tag == "member" and member.startswith("T:"):
            names.add(member[2:])

    parser.StartElementHandler = start
    parser.Parse(xml, True)
    return names


def namespace_of(type_name: str) -> str | None:
    """`System.Collections.Generic.List`1` → `System.Collections.Generic`; nested `A.B+C` → `A`."""
    outer = type_name.split("+", 1)[0].split("`", 1)[0]
    return outer.rpartition(".")[0] or None


def split_type(type_name: str) -> tuple[str, str] | None:
    """`System.Collections.Generic.List`1` → (`System.Collections.Generic`, `List`); nested types and types in the
    global namespace → None."""
    if "+" in type_name:
        return None
    namespace, _, name = type_name.split("`", 1)[0].rpartition(".")
    return (namespace, name) if namespace and name else None


def type_names(framework: str) -> set[str]:
    out: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(_download(f"{framework}.Ref"))) as pack:
        for name in pack.namelist():
            if name.startswith(f"ref/{TFM}/") and name.endswith(".xml"):
                out |= _type_names(pack.read(name))
    if not out:
        raise SystemExit(f"no documentation files under ref/{TFM}/ in {framework}.Ref {VERSION}")
    return out


def main() -> None:
    namespace_lines: set[str] = set()
    type_lines: set[str] = set()
    for framework in FRAMEWORKS:
        for t in type_names(framework):
            if ns := namespace_of(t):
                namespace_lines.add(f"{framework} {ns}")
            if parts := split_type(t):
                type_lines.add(f"{framework} {parts[0]} {parts[1]}")
    LIST.write_text("\n".join([f"# dotnet-namespaces@{VERSION}", *sorted(namespace_lines)]) + "\n", encoding="utf-8")
    TYPES.write_text("\n".join([f"# dotnet-types@{VERSION}", *sorted(type_lines)]) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
