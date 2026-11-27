import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { Answer, History, Item } from "@/api/types";
import { splitPath } from "@/graph/names";
import { TopRisks } from "@/insights/TopRisks";
import { historyLine, mapHeight, riskColor, tileLabels, tiles, Treemap } from "@/insights/Treemap";

const item = (node: string, score: number, commits: number, authors: number, transitive: number): Item =>
  ({
    node,
    kind: "file",
    confidence: "resolved",
    type_only: false,
    chain: [],
    score,
    commits,
    authors,
    transitive_dependents: transitive,
  }) as Item;
const ITEMS = [item("file:a.py", 40, 10, 1, 4), item("file:b.py", 20, 5, 2, 4), item("file:c.py", 4, 2, 3, 2)];
const HISTORY: History = {
  status: "available",
  reason: null,
  commit: "x",
  window_start: "2025-11-26T10:00:00Z",
  newest: "2026-11-26T10:00:00Z",
  oldest: "2025-12-03T08:00:00Z",
  commits_read: 312,
  merges_skipped: 4,
  shallow_skipped: 0,
  local_changes: false,
};

test("tiles: area by lines of code, all inside the box, sorted by score", () => {
  const out = tiles(
    ITEMS,
    new Map([
      ["a.py", 300],
      ["b.py", 100],
      ["c.py", 0],
    ]),
    400,
    200,
  );
  expect(out.map((t) => t.node)).toEqual(["file:a.py", "file:b.py", "file:c.py"]);
  const [a, b, c] = out.map((t) => (t.x1 - t.x0) * (t.y1 - t.y0));
  expect(a).toBeGreaterThan(b ?? Infinity);
  expect(c).toBeGreaterThan(0);
  for (const t of out) expect(t.x0 >= -1e-6 && t.y0 >= -1e-6 && t.x1 <= 400 + 1e-6 && t.y1 <= 200 + 1e-6).toBe(true);
});

test("colour from the score relative to the highest", () => {
  expect(riskColor(40, 40)).toBe("#da3633");
  expect(riskColor(0, 40)).toBe("#1f3d2b");
  expect(riskColor(20, 40)).not.toBe(riskColor(40, 40));
});

test("history line", () => {
  expect(historyLine(HISTORY)).toBe(
    "312 commits from 2025-12-03 to 2026-11-26 (window from 2025-11-26), 4 merges not counted",
  );
  expect(historyLine({ ...HISTORY, status: "not_available", reason: "zip", commits_read: 0 })).toBe(
    "history not available (zip)",
  );
  expect(
    historyLine({
      ...HISTORY,
      status: "partial",
      commits_read: 6000,
      merges_skipped: 0,
      oldest: "2026-03-01T00:00:00Z",
    }),
  ).toBe("partial history (time limit): 6000 commits read back to 2026-03-01");
  expect(historyLine({ ...HISTORY, local_changes: true })).toContain("uncommitted changes not counted");
});

test("top risks: numbers only, bus factor colours", () => {
  render(<TopRisks answer={{ items: ITEMS } as unknown as Answer} />);
  const rows = screen
    .getAllByRole("row")
    .slice(1)
    .map((r) => r.textContent);
  expect(rows).toEqual(["a.py1041", "b.py542", "c.py223"]);
  expect(screen.getByText("1")).toHaveClass("cycle");
  expect(screen.getByText("2", { selector: ".pill" })).toHaveClass("heuristic");
});

test("splitPath: file name and the folder it is in", () => {
  expect(splitPath("a.py")).toEqual({ name: "a.py", dir: "" });
  expect(splitPath("src/a/__init__.py")).toEqual({ name: "__init__.py", dir: "src/a" });
  expect(splitPath("src/a/")).toEqual({ name: "", dir: "src/a" });
});

test("top risks: a nested file shows its name over its folder, named by the full path", () => {
  const nested = [item("file:src/a/__init__.py", 9, 3, 1, 3), item("file:src/b/__init__.py", 8, 2, 2, 4)];
  render(<TopRisks answer={{ items: nested } as unknown as Answer} />);
  const first = screen.getByRole("button", { name: "src/a/__init__.py" });
  expect(first.querySelector(".path-name")).toHaveTextContent(/^__init__\.py$/);
  expect(first).toHaveAttribute("title", "src/a/__init__.py");
  expect(screen.getByRole("button", { name: "src/b/__init__.py" })).toBeInTheDocument();
  expect(screen.getByText("src/a")).toHaveClass("path-dir");
  expect(screen.getByText("src/b")).toHaveClass("path-dir");
});

test("treemap: a tile shows the file name and is named by the full path and score", () => {
  render(
    <Treemap
      items={[item("file:src/a/__init__.py", 9, 3, 1, 3)]}
      lines={new Map([["src/a/__init__.py", 10]])}
      onOpen={() => {}}
    />,
  );
  const tile = screen.getByRole("button", { name: "src/a/__init__.py, score 9" });
  expect(tile.querySelector(".name")).toHaveTextContent(/^__init__\.py$/);
});

test("treemap: a tile shows only the labels that fit, never a few cut letters", () => {
  expect(tileLabels(200, 80)).toEqual({ name: true, score: true });
  expect(tileLabels(60, 30)).toEqual({ name: true, score: false });
  expect(tileLabels(40, 80)).toEqual({ name: false, score: false });
  expect(tileLabels(200, 20)).toEqual({ name: false, score: false });
});

test("treemap: the map height follows the width within bounds", () => {
  expect(mapHeight(300)).toBe(280);
  expect(mapHeight(800)).toBe(496);
  expect(mapHeight(2000)).toBe(560);
});
