import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { Answer, Item } from "@/api/types";
import { ImpactPanel, impactByComponent } from "@/graph/ImpactPanel";

const item = (node: string, confidence: "resolved" | "heuristic" = "resolved"): Item => ({
  node,
  kind: "file",
  confidence,
  type_only: false,
  chain: [],
});

const COMPONENTS = {
  components: [
    { id: "component:1", name: "auth", files: ["file:a1", "file:a2"], file_count: 2, has_cycle: false },
    { id: "component:2", name: "api", files: ["file:b1", "file:b2", "file:b3"], file_count: 3, has_cycle: false },
    { id: "component:3", name: "web", files: ["file:w1", "file:w2"], file_count: 2, has_cycle: false },
  ],
  links: [],
} as unknown as Answer;

const IMPACT = {
  question: "impact",
  target: "file:a1",
  total: 7,
  truncated: true,
  items: [
    item("file:a2"),
    item("file:b1"),
    item("file:b2"),
    item("file:b3"),
    item("file:w1", "heuristic"),
    item("file:w2", "heuristic"),
  ],
} as unknown as Answer;

test("counts per component, heuristic apart", () => {
  expect(impactByComponent(IMPACT, COMPONENTS)).toEqual([
    { id: "component:2", name: "api", resolved: 3, heuristic: 0, color: 2 },
    { id: "component:3", name: "web", resolved: 0, heuristic: 2, color: 3 },
    { id: "component:1", name: "auth", resolved: 1, heuristic: 0, color: 1 },
  ]);
});

test("panel", () => {
  render(<ImpactPanel answer={IMPACT} components={COMPONENTS} />);
  expect(screen.getByText("7")).toBeInTheDocument();
  expect(screen.getByText("files in 3 components")).toBeInTheDocument();
  expect(screen.getByText("~2 heuristic")).toBeInTheDocument();
  expect(screen.getByText("and 1 more (the list is cut)")).toBeInTheDocument();
  expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["api3", "web~2 heuristic", "auth1"]);
});

test("nothing depends on the file", () => {
  render(<ImpactPanel answer={{ ...IMPACT, total: 0, truncated: false, items: [] }} components={COMPONENTS} />);
  expect(screen.getByText("Nothing depends on this file.")).toBeInTheDocument();
});
