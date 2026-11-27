import { expect, test } from "vitest";

import type { Answer, GraphDocument } from "@/api/types";
import { isTest, toElements, type ElementsInput } from "@/graph/elements";
import { componentLabel } from "@/graph/names";

type E = { source: string; target: string; confidence?: string; type_only?: boolean; type?: string };

function doc(files: string[], edges: E[], externals: string[] = []): GraphDocument {
  return {
    snapshot: "content:1",
    nodes: [
      ...files.map((path) => ({ id: `file:${path}`, kind: "file", path, language: "python", definitions: [] })),
      ...externals.map((name) => ({
        id: `ext:python:${name}`,
        kind: "external",
        name,
        ecosystem: "python",
        category: "third_party",
      })),
      { id: "unresolved:python:gone", kind: "unresolved", reference: "gone", ecosystem: "python" },
    ],
    edges: edges.map((e, i) => ({
      id: `e${i}`,
      line: i + 1,
      type: e.type ?? "imports",
      confidence: e.confidence ?? "resolved",
      type_only: e.type_only ?? false,
      ...e,
    })),
    coverage: {
      files: files.map((path) => ({ path, language: "python", status: "analyzed", flags: [] })),
      skipped: [],
    },
  } as unknown as GraphDocument;
}

const COMPONENTS = {
  components: [
    { id: "component:1", name: "a", files: ["file:a/x.py", "file:a/y.py"], file_count: 2, has_cycle: true },
    { id: "component:2", name: "b", files: ["file:b/z.py", "file:b/tests/test_z.py"], file_count: 2, has_cycle: false },
  ],
  links: [
    { source: "component:1", target: "component:2", imports: 3, heuristic: 1, in_cycle: false },
    { source: "component:2", target: "component:1", imports: 1, heuristic: 0, in_cycle: true },
  ],
} as unknown as Answer;

const GRAPH = doc(
  ["a/x.py", "a/y.py", "b/z.py", "b/tests/test_z.py"],
  [
    { source: "file:a/x.py", target: "file:a/y.py" },
    { source: "file:a/y.py", target: "file:a/x.py" },
    { source: "file:a/x.py", target: "file:b/z.py" },
    { source: "file:a/x.py", target: "file:b/z.py", type_only: true },
    { source: "file:a/y.py", target: "file:b/z.py", confidence: "heuristic", type: "http_call" },
    { source: "file:b/tests/test_z.py", target: "file:b/z.py" },
    { source: "file:b/z.py", target: "ext:python:requests" },
    { source: "file:b/z.py", target: "unresolved:python:gone", confidence: "unresolved" },
    { source: "file:a/x.py", target: "file:a/x.py", type_only: true },
  ],
  ["requests"],
);

const base: ElementsInput = {
  level: "system",
  component: null,
  components: COMPONENTS,
  graph: GRAPH,
  hide: [],
  selected: null,
  impact: null,
};

const ids = (els: ReturnType<typeof toElements>, group: "nodes" | "edges") =>
  els.filter((e) => (group === "edges") === "source" in e.data).map((e) => e.data.id);

test("system level: components and component links", () => {
  const els = toElements(base);
  expect(ids(els, "nodes")).toEqual(["component:1", "component:2"]);
  const nodes = els.filter((e) => !("source" in e.data));
  expect(nodes[0]?.data).toMatchObject({ label: "a", count: 2, color: 1 });
  expect(nodes[0]?.classes).toContain("cycle");
  const edges = els.filter((e) => "source" in e.data);
  expect(edges.map((e) => [e.data.source, e.data.target, e.data.imports, e.classes])).toEqual([
    ["component:1", "component:2", 3, "link heuristic"],
    ["component:2", "component:1", 1, "link cycle"],
  ]);
});

test("component level: one component expanded, the others collapsed", () => {
  const els = toElements({ ...base, level: "component", component: "component:1" });
  expect(ids(els, "nodes")).toEqual(["component:1", "file:a/x.py", "file:a/y.py", "component:2"]);
  const x = els.find((e) => e.data.id === "file:a/x.py");
  expect(x?.data).toMatchObject({ parent: "component:1", label: "x.py" });
  expect(els.find((e) => e.data.id === "component:1")?.classes).toContain("expanded");
  const edges = els.filter((e) => "source" in e.data).map((e) => [e.data.source, e.data.target, e.classes]);
  expect(edges).toEqual([
    ["file:a/x.py", "file:a/x.py", "link type-only"],
    ["file:a/x.py", "file:a/y.py", "link"],
    ["file:a/y.py", "file:a/x.py", "link"],
    ["file:a/x.py", "component:2", "link"],
    ["file:a/y.py", "component:2", "link heuristic"],
    ["component:2", "component:1", "link cycle"],
  ]);
});

const notClusters = (els: ReturnType<typeof toElements>) => els.filter((e) => e.data.kind !== "cluster");

test("file level: file links from the graph, unresolved never drawn, externals and tests can be hidden", () => {
  const els = toElements({ ...base, level: "file" });
  expect(ids(notClusters(els), "nodes")).toEqual([
    "file:a/x.py",
    "file:a/y.py",
    "file:b/tests/test_z.py",
    "file:b/z.py",
    "ext:python:requests",
  ]);
  const edges = els.filter((e) => "source" in e.data);
  expect(edges.map((e) => [e.data.source, e.data.target, e.classes])).toEqual([
    ["file:a/x.py", "file:a/x.py", "link type-only"],
    ["file:a/x.py", "file:a/y.py", "link"],
    ["file:a/x.py", "file:b/z.py", "link"],
    ["file:a/y.py", "file:a/x.py", "link"],
    ["file:a/y.py", "file:b/z.py", "link heuristic"],
    ["file:b/tests/test_z.py", "file:b/z.py", "link"],
    ["file:b/z.py", "ext:python:requests", "link external"],
  ]);
  expect(edges.find((e) => e.data.source === "file:a/x.py" && e.data.target === "file:b/z.py")?.data.imports).toBe(2);
  const hidden = toElements({ ...base, level: "file", hide: ["external", "tests"] });
  expect(ids(notClusters(hidden), "nodes")).toEqual(["file:a/x.py", "file:a/y.py", "file:b/z.py"]);
  expect(ids(hidden, "nodes")).not.toContain("cluster:external");
  expect(ids(hidden, "edges").some((id) => String(id).includes("requests") || String(id).includes("test_z"))).toBe(
    false,
  );
});

test("file nodes carry their component colour", () => {
  const els = toElements({ ...base, level: "file" });
  expect(els.find((e) => e.data.id === "file:b/z.py")?.data.color).toBe(2);
});

test("selection and impact classes", () => {
  const els = toElements({ ...base, level: "file", selected: "file:b/z.py", impact: new Set(["file:a/x.py"]) });
  const cls = (id: string) => els.find((e) => e.data.id === id)?.classes ?? "";
  expect(cls("file:b/z.py")).toContain("selected");
  expect(cls("file:a/x.py")).toContain("impacted");
  expect(cls("file:a/y.py")).toContain("dimmed");
  expect(cls("file:a/x.py->file:b/z.py")).toContain("impact");
  expect(cls("file:a/y.py->file:a/x.py")).toContain("dimmed");
});

test("collapsed components show their impact count", () => {
  const els = toElements({
    ...base,
    level: "component",
    component: "component:1",
    impact: new Set(["file:b/z.py", "file:b/tests/test_z.py"]),
  });
  expect(els.find((e) => e.data.id === "component:2")?.data.impacted).toBe(2);
  expect(els.find((e) => e.data.id === "component:1")?.classes).not.toContain("dimmed");
});

test("is test", () => {
  for (const p of ["tests/a.py", "src/test/b.ts", "a/__tests__/c.ts", "a/x_test.go", "a/x.test.ts", "a/x.spec.tsx"]) {
    expect(isTest(p)).toBe(true);
  }
  for (const p of ["src/testing.py", "contest.py", "latest/a.py"]) expect(isTest(p)).toBe(false);
});

test("no links and one file", () => {
  const alone = doc(["main.py"], []);
  const comps = {
    components: [{ id: "component:1", name: ".", files: ["file:main.py"], file_count: 1, has_cycle: false }],
    links: [],
  } as unknown as Answer;
  for (const level of ["system", "component", "file"] as const) {
    const els = toElements({ ...base, graph: alone, components: comps, level, component: "component:1" });
    expect(ids(els, "edges")).toEqual([]);
    expect(ids(els, "nodes").length).toBeGreaterThan(0);
  }
});

test("links inside a cycle group are marked", () => {
  const cycles = {
    groups: [{ files: ["file:a/x.py", "file:a/y.py"], cycle: [], type_only: false, confidence: "resolved" }],
  } as unknown as Answer;
  const els = toElements({ ...base, level: "file", cycles });
  const cls = (id: string) => els.find((e) => e.data.id === id)?.classes ?? "";
  expect(cls("file:a/x.py->file:a/y.py")).toBe("link cycle");
  expect(cls("file:a/x.py->file:b/z.py")).toBe("link");
  const inside = toElements({ ...base, level: "component", component: "component:1", cycles });
  expect(inside.find((e) => e.data.id === "file:a/y.py->file:a/x.py")?.classes).toBe("link cycle");
});

test("long component names are shortened from the left on the graph", () => {
  expect(componentLabel("fixtures/repos/csharp-multiproject/repo/src")).toBe("…/csharp-multiproject/repo/src");
  expect(componentLabel("fixtures/repos/ts-barrels/repo/src/types · 2")).toBe("…/ts-barrels/repo/src/types · 2");
  expect(componentLabel("backend")).toBe("backend");
  expect(componentLabel("src/auth · 3")).toBe("src/auth · 3");
  expect(componentLabel("a-very-long-single-folder-name-without-any-slash-in-it")).toBe(
    "a-very-long-single-folder-name-without-any-slash-in-it",
  );
});

test("file level: files sit in a cluster per component, sized by their importers", () => {
  const els = toElements({ ...base, level: "file" });
  const data = (id: string) => els.find((e) => e.data.id === id)?.data ?? {};
  expect(els.filter((e) => e.data.kind === "cluster").map((e) => [e.data.id, e.data.label])).toEqual([
    ["cluster:component:1", "a (2)"],
    ["cluster:component:2", "b (2)"],
    ["cluster:external", "external (1)"],
  ]);
  expect(data("file:a/x.py").parent).toBe("cluster:component:1");
  expect(data("ext:python:requests").parent).toBe("cluster:external");
  // b/z.py is imported by three files, a/y.py by one: the dot of the most imported file is the biggest
  expect(Number(data("file:b/z.py").size)).toBeGreaterThan(Number(data("file:a/y.py").size));
  expect(data("file:b/z.py").major).toBe(true);
  expect(els.find((e) => e.data.id === "file:a/x.py->file:b/z.py")?.data.cross).toBe(true);
  expect(els.find((e) => e.data.id === "file:a/x.py->file:a/y.py")?.data.cross).toBe(false);
});
