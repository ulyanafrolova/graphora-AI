"""tsconfig/jsconfig reading (specs/003-ts-js-analysis research.md § R4, data-model.md § Coverage)."""

import json

import pytest

from graphora.resolve.tsconfig import load_configs, parse_jsonc


def _configs(files: dict[str, str]):
    data = {path: text.encode("utf-8") for path, text in files.items()}
    return load_configs(frozenset(data), data.__getitem__)


# --- JSONC ----------------------------------------------------------------------------------


def test_jsonc_comments_and_trailing_commas():
    text = '{\n  // line\n  "a": "x//y", /* block */ "b": [1, 2,],\n  "c": "/* not a comment */",\n}\n'
    assert parse_jsonc(text) == {"a": "x//y", "b": [1, 2], "c": "/* not a comment */"}


def test_jsonc_escaped_quote_in_string():
    assert parse_jsonc('{"a": "q\\"//x", }') == {"a": 'q"//x'}


@pytest.mark.parametrize("text", ["[1, 2]", "{", "not json", '{"a": 1} trailing', ""])
def test_jsonc_invalid_or_not_object(text):
    assert parse_jsonc(text) is None


# --- nearest config ---------------------------------------------------------------------------


def _paths_config(base_url=".", paths=None, extends=None):
    options = {"baseUrl": base_url}
    if paths is not None:
        options["paths"] = paths
    config = {"compilerOptions": options}
    if extends is not None:
        config["extends"] = extends
    return json.dumps(config)


def test_nearest_ancestor_wins():
    configs = _configs({"tsconfig.json": _paths_config("root"), "web/tsconfig.json": _paths_config("src")})
    assert configs.for_file("web/a/b.ts").base_url == "web/src"
    assert configs.for_file("api/x.ts").base_url == "root"


def test_tsconfig_beats_jsconfig_in_same_folder():
    configs = _configs({"tsconfig.json": _paths_config("ts"), "jsconfig.json": _paths_config("js")})
    assert configs.for_file("a.js").base_url == "ts"


def test_no_config():
    effective = _configs({"a.ts": ""}).for_file("a.ts")
    assert (effective.base_url, effective.paths) == (None, ())


# --- extends ----------------------------------------------------------------------------------


def test_extends_without_json_suffix():
    configs = _configs({"tsconfig.json": '{"extends": "./tsconfig.base"}', "tsconfig.base.json": _paths_config("src")})
    assert configs.for_file("a.ts").base_url == "src"


def test_extends_array_later_entries_win_and_own_options_last():
    configs = _configs(
        {
            "tsconfig.json": json.dumps({"extends": ["./a.json", "./b.json"], "compilerOptions": {"paths": {"x": ["own"]}}}),
            "a.json": _paths_config("from-a", {"x": ["a"]}),
            "b.json": _paths_config("from-b"),
        }
    )
    effective = configs.for_file("m.ts")
    assert effective.base_url == "from-b"
    assert effective.paths == (("x", ("from-b/own",)),)


@pytest.mark.parametrize("target", ["@tsconfig/node20/tsconfig.json", "/abs/tsconfig.json", "../outside.json", "./missing"])
def test_extends_ignored_targets(target):
    configs = _configs({"tsconfig.json": json.dumps({"extends": target, "compilerOptions": {"baseUrl": "own"}})})
    assert configs.for_file("a.ts").base_url == "own"


def test_extends_cycle_stops():
    configs = _configs({"tsconfig.json": '{"extends": "./a.json"}', "a.json": _paths_config("a", extends="./tsconfig.json")})
    assert configs.for_file("x.ts").base_url == "a"


# --- anchoring --------------------------------------------------------------------------------


def test_base_url_relative_to_defining_config():
    configs = _configs({"web/tsconfig.json": '{"extends": "../base/tsconfig.json"}', "base/tsconfig.json": _paths_config("src")})
    assert configs.for_file("web/a.ts").base_url == "base/src"


def test_paths_relative_to_base_url_or_defining_folder():
    with_base = _configs({"web/tsconfig.json": _paths_config("src", {"@/*": ["app/*"]})})
    assert with_base.for_file("web/a.ts").paths == (("@/*", ("web/src/app/*",)),)
    without_base = _configs({"web/tsconfig.json": json.dumps({"compilerOptions": {"paths": {"@/*": ["./app/*"]}}})})
    assert without_base.for_file("web/a.ts").paths == (("@/*", ("web/app/*",)),)


def test_paths_order_exact_then_longest_prefix():
    paths = {"*": ["any/*"], "@a/*": ["a/*"], "@a/b/*": ["ab/*"], "@a/b": ["exact"]}
    configs = _configs({"tsconfig.json": _paths_config(".", paths)})
    assert [p for p, _ in configs.for_file("x.ts").paths] == ["@a/b", "@a/b/*", "@a/*", "*"]


def test_paths_targets_outside_root_dropped():
    configs = _configs({"tsconfig.json": _paths_config(".", {"x": ["../out/x", "in/x"]})})
    assert configs.for_file("a.ts").paths == (("x", ("in/x",)),)


# --- broken configs ---------------------------------------------------------------------------


def test_broken_configs_reported_and_treated_as_absent():
    configs = _configs(
        {
            "tsconfig.json": _paths_config("root"),
            "web/tsconfig.json": "{ broken",
            "unused/jsconfig.json": "[]",
        }
    )
    assert configs.invalid == ("unused/jsconfig.json", "web/tsconfig.json")
    assert configs.for_file("web/a.ts").base_url == "root"


def test_broken_extends_target_skipped_and_reported():
    configs = _configs(
        {
            "tsconfig.json": json.dumps({"extends": ["./bad.json", "./good.json"]}),
            "bad.json": "{ nope",
            "good.json": _paths_config("g"),
        }
    )
    assert configs.for_file("a.ts").base_url == "g"
    assert configs.invalid == ("bad.json",)
