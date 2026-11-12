"""Regenerate src/graphora/resolve/data/implicit_usings.txt (specs/008-csharp-type-references research.md § R4).

Needs network access to raw.githubusercontent.com. Downloads the .NET SDK's own props files at pinned tags and keeps
the `<Using Include>` items of item groups whose `Condition` tests `ImplicitUsings`: that is how the SDK itself
defines implicit global usings. Reads XML as data (DTDs refused); never runs .NET and is never run by tests or
`graphora analyze`:

    uv run python scripts/gen_implicit_usings.py

WPF defines no implicit usings of its own (checked for `dotnet/wpf` v10.0.0), so there is no `wpf` group.
Bump IMPLICIT_USINGS_VERSION in graphora.resolve.csharp and VERSION below when the list changes.
"""

import urllib.request
from pathlib import Path
from xml.parsers import expat

VERSION = "10.0.100"
RAW = "https://raw.githubusercontent.com"
SOURCES = (
    ("base", "dotnet/sdk/v10.0.100/src/Tasks/Microsoft.NET.Build.Tasks/targets/Microsoft.NET.Sdk.CSharp.props"),
    ("web", "dotnet/sdk/v10.0.100/src/WebSdk/Web/Targets/Sdk.Server.props"),
    ("worker", "dotnet/sdk/v10.0.100/src/WebSdk/Worker/Targets/Microsoft.NET.Sdk.Worker.props"),
    (
        "winforms",
        "dotnet/winforms/v10.0.0/pkg/Microsoft.Private.Winforms/sdk/dotnet-wpf/Microsoft.NET.Sdk.WindowsDesktop.WindowsForms.props",
    ),
)
LIST = Path(__file__).resolve().parents[1] / "src" / "graphora" / "resolve" / "data" / "implicit_usings.txt"


def _download(path: str) -> bytes:
    with urllib.request.urlopen(f"{RAW}/{path}", timeout=60) as response:  # noqa: S310 (fixed https URL)
        return response.read()


def _refuse_doctype(*_args: object) -> None:
    raise ValueError("DOCTYPE not allowed")


def implicit_usings(xml: bytes) -> set[str]:
    """`<Using Include>` items inside an ItemGroup whose Condition mentions ImplicitUsings."""
    out: set[str] = set()
    groups: list[bool] = []
    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = _refuse_doctype

    def start(tag: str, attrs: dict[str, str]) -> None:
        if tag == "ItemGroup":
            groups.append("ImplicitUsings" in attrs.get("Condition", ""))
        elif tag == "Using" and groups and groups[-1] and "Include" in attrs:
            out.add(attrs["Include"].strip())

    def end(tag: str) -> None:
        if tag == "ItemGroup":
            groups.pop()

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.Parse(xml, True)
    return out


def main() -> None:
    lines = set()
    for group, path in SOURCES:
        found = implicit_usings(_download(path))
        if not found:
            raise SystemExit(f"no implicit usings found in {path}")
        lines |= {f"{group} {namespace}" for namespace in found}
    LIST.write_text("\n".join([f"# dotnet-implicit-usings@{VERSION}", *sorted(lines)]) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
