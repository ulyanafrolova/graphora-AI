import { expect, test } from "vitest";

import { DEFAULT, parseRoute, switchSnapshot, toPath, type RouteState } from "@/state/route";

const full: RouteState = {
  ...DEFAULT,
  repository: "github.com/o/r",
  snapshot: "content:abc",
  screen: "graph",
  level: "component",
  component: "component:2",
  node: "file:src/a b.py",
  impact: true,
  hide: ["external", "tests"],
};

test("round trip through the address", () => {
  const path = toPath(full);
  expect(path).toBe(
    "/r/github.com%2Fo%2Fr/content%3Aabc/graph?level=component&component=component%3A2&node=file%3Asrc%2Fa%20b.py&impact=on&hide=external%2Ctests",
  );
  const [pathname, search] = path.split("?");
  expect(parseRoute(pathname ?? "", `?${search}`)).toEqual(full);
});

test("defaults are left out of the address", () => {
  expect(toPath({ ...DEFAULT, repository: "r", snapshot: "s", screen: "graph" })).toBe("/r/r/s/graph");
});

test("code view keeps path and line", () => {
  const state = { ...DEFAULT, repository: "r", snapshot: "s", screen: "code" as const, path: "src/x.py", line: 12 };
  expect(parseRoute("/r/r/s/code", "?path=src%2Fx.py&line=12")).toEqual(state);
  expect(toPath(state)).toBe("/r/r/s/code?path=src%2Fx.py&line=12");
});

test("unknown values fall back to defaults", () => {
  const parsed = parseRoute("/r/r/s/graph", "?level=galaxy&impact=maybe&hide=tests,nonsense&line=x");
  expect(parsed).toEqual({ ...DEFAULT, repository: "r", snapshot: "s", screen: "graph", hide: ["tests"] });
});

test("unknown screens and other paths are not snapshot routes", () => {
  expect(parseRoute("/r/r/s/nope", "")).toBeNull();
  expect(parseRoute("/import", "")).toBeNull();
  expect(parseRoute("/r/r", "")).toBeNull();
});

test("every screen parses", () => {
  for (const screen of [
    "graph",
    "code",
    "ask",
    "trace",
    "cycles",
    "hotspots",
    "pr-impact",
    "security",
    "mcp",
  ] as const) {
    expect(parseRoute(`/r/r/s/${screen}`, "")?.screen).toBe(screen);
  }
});

test("switching snapshot keeps a node that exists and clears the rest", () => {
  const kept = switchSnapshot(full, "github.com/o/r", "content:def", () => true);
  expect(kept.note).toBeNull();
  expect(kept.state).toMatchObject({
    snapshot: "content:def",
    node: "file:src/a b.py",
    component: null,
    impact: false,
    level: "system",
  });
  const cleared = switchSnapshot(full, "github.com/o/r", "content:def", () => false);
  expect(cleared.note).toBe("selection cleared: not in this snapshot");
  expect(cleared.state.node).toBeNull();
});
