"""TS/JS specifier resolution, one test per row of specs/003-ts-js-analysis/data-model.md § Resolution."""

import json

import pytest

from graphora.adapters.js.extract import ImportName, ImportRecord
from graphora.resolve.js import JsResolver, category, workspace_names
from graphora.resolve.tsconfig import load_configs


def _resolver(files, analyzed=None, configs=None, workspaces=()):
    files = frozenset(files) | frozenset(configs or {})
    data = {p: (configs or {}).get(p, "").encode() for p in files}
    analyzed = frozenset(analyzed if analyzed is not None else (f for f in files if f.endswith((".ts", ".tsx", ".js", ".mjs", ".cjs", ".jsx", ".mts", ".cts"))))
    return JsResolver(files, analyzed, load_configs(files, data.__getitem__), frozenset(workspaces))


def _record(specifier, text=None):
    return ImportRecord("imports", "static", specifier, (ImportName(None, False),), text or f'import "{specifier}"', 1, 1)


def _resolve(resolver, specifier, source="src/app.ts", text=None):
    return resolver.resolve(source, _record(specifier, text))


# --- relative: try() order ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "files, expected",
    [
        (["src/m"], "src/m"),
        (["src/m.ts", "src/m.js"], "src/m.ts"),
        (["src/m.tsx", "src/m.d.ts"], "src/m.tsx"),
        (["src/m.d.ts", "src/m.mts"], "src/m.d.ts"),
        (["src/m.js", "src/m.json"], "src/m.js"),
        (["src/m.json"], "src/m.json"),
        (["src/m/index.ts", "src/m/index.js"], "src/m/index.ts"),
    ],
)
def test_try_order(files, expected):
    node_id, reason = _resolve(_resolver(files), "./m")
    assert reason is None and node_id.endswith(":" + expected)


def test_file_beats_folder_index():
    assert _resolve(_resolver(["src/foo.ts", "src/foo/index.ts"]), "./foo") == ("file:src/foo.ts", None)


@pytest.mark.parametrize(
    "specifier, files, expected",
    [
        ("./util.js", ["src/util.ts"], "src/util.ts"),
        ("./util.js", ["src/util.tsx"], "src/util.tsx"),
        ("./types.js", ["src/types.d.ts"], "src/types.d.ts"),
        ("./types.js", ["src/types.tsx", "src/types.d.ts"], "src/types.tsx"),
        ("./util.js", ["src/util.js", "src/util.ts"], "src/util.js"),
        ("./c.jsx", ["src/c.tsx"], "src/c.tsx"),
        ("./m.mjs", ["src/m.mts"], "src/m.mts"),
        ("./m.cjs", ["src/m.cts"], "src/m.cts"),
    ],
)
def test_js_to_ts_extension(specifier, files, expected):
    assert _resolve(_resolver(files), specifier) == (f"file:{expected}", None)


def test_asset_vs_file():
    resolver = _resolver(["src/styles.css", "src/data.json", "src/b.ts"])
    assert _resolve(resolver, "./styles.css") == ("asset:src/styles.css", None)
    assert _resolve(resolver, "./data.json") == ("asset:src/data.json", None)
    assert _resolve(resolver, "./data") == ("asset:src/data.json", None)
    assert _resolve(resolver, "../src/b") == ("file:src/b.ts", None)


@pytest.mark.parametrize(
    "specifier, source, expected",
    [
        ("./", "src/sub/x.ts", "src/sub/index.ts"),
        (".", "src/sub/x.ts", "src/sub/index.ts"),
        ("..", "src/sub/x.ts", "src/index.ts"),
        ("../..", "src/sub/x.ts", "index.ts"),
        ("../lib/", "src/sub/x.ts", "src/lib/index.ts"),
    ],
)
def test_folder_specifier_never_tries_sibling_file(specifier, source, expected):
    files = ["src.ts", "src/sub.ts", "src/lib.ts", "index.ts", "src/index.ts", "src/sub/index.ts", "src/lib/index.ts"]
    assert _resolve(_resolver(files), specifier, source) == (f"file:{expected}", None)


def test_folder_specifier_without_index_is_not_found():
    assert _resolve(_resolver(["src/lib.ts"]), "./lib/") == ("unresolved:npm:src/lib", "not_found")


def test_missing_relative_uses_normalized_path():
    assert _resolve(_resolver([]), "./missing") == ("unresolved:npm:src/missing", "not_found")
    assert _resolve(_resolver([]), "../x/../y") == ("unresolved:npm:y", "not_found")


def test_relative_above_root():
    assert _resolve(_resolver([]), "../../outside") == ("unresolved:npm:../../outside", "not_found")


def test_dot_specifier_resolves_index():
    assert _resolve(_resolver(["src/index.ts"]), ".") == ("file:src/index.ts", None)
    assert _resolve(_resolver(["index.js"]), ".", source="a.js") == ("file:index.js", None)


@pytest.mark.parametrize("specifier", ["/abs/x", "https://cdn.example/x.js", "data:text/javascript,1", "#internal", "file:./x"])
def test_never_resolved_forms(specifier):
    assert _resolve(_resolver([]), specifier) == (f"unresolved:npm:{specifier}", "not_found")


# --- built-ins and packages --------------------------------------------------------------------


@pytest.mark.parametrize("specifier", ["fs", "node:fs", "fs/promises", "node:fs/promises"])
def test_builtin_fs(specifier):
    assert _resolve(_resolver([]), specifier) == ("ext:npm:fs", None)
    assert category("fs") == "builtin"


def test_prefix_only_builtin():
    resolver = _resolver([])
    assert _resolve(resolver, "node:test") == ("ext:npm:node:test", None)
    assert _resolve(resolver, "node:test/reporters") == ("ext:npm:node:test", None)
    assert category("node:test") == "builtin"
    assert _resolve(resolver, "test") == ("ext:npm:test", None)
    assert category("test") == "third_party"
    assert _resolve(resolver, "node:nope") == ("unresolved:npm:node:nope", "not_found")


@pytest.mark.parametrize(
    "specifier, package",
    [("react", "react"), ("lodash/fp", "lodash"), ("@scope/pkg", "@scope/pkg"), ("@scope/pkg/deep/x", "@scope/pkg")],
)
def test_package_names(specifier, package):
    assert _resolve(_resolver([]), specifier) == (f"ext:npm:{package}", None)
    assert category(package) == "third_party"


@pytest.mark.parametrize("specifier", ["@scope", "@scope/", "@/x", ""])
def test_invalid_package_names(specifier):
    reference = specifier or 'import ""'  # an empty specifier falls back to the statement as written
    assert _resolve(_resolver([]), specifier) == (f"unresolved:npm:{reference}", "not_found")


def test_dynamic_record():
    record = ImportRecord("imports", "dynamic", None, (ImportName(None, False),), "import(`./p/${n}`)", 1, 1)
    assert _resolver([]).resolve("src/a.ts", record) == ("unresolved:npm:import(`./p/${n}`)", "dynamic")


# --- tsconfig paths and baseUrl ----------------------------------------------------------------


def _tsconfig(base_url=None, paths=None):
    options = {}
    if base_url is not None:
        options["baseUrl"] = base_url
    if paths is not None:
        options["paths"] = paths
    return {"tsconfig.json": json.dumps({"compilerOptions": options})}


def test_paths_exact_beats_star_and_longest_prefix_wins():
    configs = _tsconfig(".", {"@app/*": ["src/*"], "@app/core/*": ["core/*"], "@lib": ["src/lib/index.ts"]})
    resolver = _resolver(["src/x.ts", "core/y.ts", "src/lib/index.ts", "src/core/y.ts"], configs=configs)
    assert _resolve(resolver, "@app/x") == ("file:src/x.ts", None)
    assert _resolve(resolver, "@app/core/y") == ("file:core/y.ts", None)
    assert _resolve(resolver, "@lib") == ("file:src/lib/index.ts", None)


def test_paths_targets_in_order():
    resolver = _resolver(["b/x.ts"], configs=_tsconfig(".", {"@/*": ["a/*", "b/*"]}))
    assert _resolve(resolver, "@/x") == ("file:b/x.ts", None)


def test_paths_miss_falls_through_but_tries_no_later_pattern():
    configs = _tsconfig(".", {"@app/*": ["src/*"], "*": ["fallback/*"]})
    resolver = _resolver(["fallback/@app/missing.ts", "src/x.ts"], configs=configs)
    assert _resolve(resolver, "@app/missing") == ("ext:npm:@app/missing", None)
    assert _resolve(resolver, "@app/x") == ("file:src/x.ts", None)


def test_catch_all_paths_keep_packages_and_builtins():
    resolver = _resolver(["types/foo.d.ts"], configs=_tsconfig(None, {"*": ["types/*"]}))
    assert _resolve(resolver, "foo") == ("file:types/foo.d.ts", None)
    assert _resolve(resolver, "react") == ("ext:npm:react", None)
    assert _resolve(resolver, "fs/promises") == ("ext:npm:fs", None)


def test_paths_miss_then_base_url_hit():
    resolver = _resolver(["src/util.ts"], configs=_tsconfig("src", {"*": ["types/*"]}))
    assert _resolve(resolver, "util") == ("file:src/util.ts", None)


def test_base_url_hit_and_fall_through():
    resolver = _resolver(["src/config.ts"], configs=_tsconfig("src"))
    assert _resolve(resolver, "config") == ("file:src/config.ts", None)
    assert _resolve(resolver, "react") == ("ext:npm:react", None)
    assert _resolve(resolver, "fs") == ("ext:npm:fs", None)


def test_paths_can_shadow_builtin():
    resolver = _resolver(["shim/fs.ts"], configs=_tsconfig(".", {"fs": ["shim/fs.ts"]}))
    assert _resolve(resolver, "fs") == ("file:shim/fs.ts", None)


# --- workspaces (FR-010) -----------------------------------------------------------------------


def test_workspace_package():
    resolver = _resolver([], workspaces={"@acme/ui"})
    assert _resolve(resolver, "@acme/ui") == ("unresolved:npm:@acme/ui", "workspace_package")
    assert _resolve(resolver, "@acme/ui/button") == ("unresolved:npm:@acme/ui/button", "workspace_package")


def test_paths_alias_beats_workspace():
    resolver = _resolver(["packages/ui/src/index.ts"], configs=_tsconfig(".", {"@acme/ui": ["packages/ui/src/index.ts"]}), workspaces={"@acme/ui"})
    assert _resolve(resolver, "@acme/ui") == ("file:packages/ui/src/index.ts", None)


def test_workspace_names():
    contents = {
        "package.json": b'{"name": "root-app", "workspaces": ["packages/*"]}',
        "packages/ui/package.json": b'{"name": "@acme/ui"}',
        "packages/ui2/package.json": b'{"name": "@acme/ui"}',
        "packages/bad/package.json": b"{ not json",
        "packages/noname/package.json": b'{"version": "1.0.0"}',
        "packages/numname/package.json": b'{"name": 5}',
        "src/a.ts": b"",
    }
    assert workspace_names(frozenset(contents), contents.__getitem__) == frozenset({"@acme/ui"})
