import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { Answer, History, Item } from "@/api/types";
import { TopRisks } from "@/insights/TopRisks";
import { historyLine, riskColor, tiles } from "@/insights/Treemap";

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
  for (const t of out) expect(t.x0 >= 0 && t.y0 >= 0 && t.x1 <= 400 && t.y1 <= 200).toBe(true);
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
  expect(historyLine({ ...HISTORY, status: "partial", commits_read: 6000, oldest: "2026-03-01T00:00:00Z" })).toBe(
    "partial history (time limit): 6000 commits read back to 2026-03-01",
  );
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
