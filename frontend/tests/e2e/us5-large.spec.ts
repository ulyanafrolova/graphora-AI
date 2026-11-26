/// <reference lib="dom" />
import { expect, type Page, test } from "@playwright/test";

import { at, graphReady, nodesWith, snapshotOf } from "./helpers";

// SC-003 is for a developer laptop; the CI runner is slower
const BUDGET = process.env.CI ? 2000 : 1000;

/** Milliseconds from the click to the graph showing a new set of nodes, measured inside the page. */
async function timeExpand(page: Page): Promise<number> {
  await page.evaluate(() => {
    const graph = document.querySelector('[data-testid="graph"]');
    const w = window as unknown as { clicked: number; drawn: number };
    w.drawn = 0;
    document.addEventListener("click", () => (w.clicked = performance.now()), { capture: true, once: true });
    new MutationObserver((_, observer) => {
      w.drawn = performance.now();
      observer.disconnect();
    }).observe(graph as Node, { attributeFilter: ["data-nodes"] });
  });
  await page.getByRole("button", { name: "Expand component" }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { drawn: number }).drawn)).toBeGreaterThan(0);
  return page.evaluate(() => {
    const w = window as unknown as { clicked: number; drawn: number };
    return w.drawn - w.clicked;
  });
}

test("a 5,000-file snapshot stays responsive", async ({ page, request }) => {
  const snap = await snapshotOf(request, "large");
  const started = Date.now();
  await page.goto(at("large", snap, "graph"));
  await graphReady(page);
  expect(Date.now() - started).toBeLessThan(5000);
  await expect(page.getByTestId("stat-files")).toContainText("5 000");

  await page.goto(at("large", snap, "graph", "node=component%3A1"));
  await graphReady(page);
  expect(await timeExpand(page)).toBeLessThan(BUDGET);
  await expect(page).toHaveURL(/level=component/);
  expect(Number(await page.getByTestId("graph").getAttribute("data-nodes"))).toBeGreaterThan(1000);

  const fetched = page.waitForResponse((r) => r.url().includes("/api/v1/impact"));
  await page.goto(at("large", snap, "graph", "level=component&component=component%3A1&node=file%3Apkg18%2Fm1894.py"));
  await graphReady(page);
  await fetched;
  const t = Date.now();
  await page.getByRole("button", { name: "Impact mode" }).click();
  await expect.poll(async () => (await nodesWith(page, "impacted")).length, { timeout: BUDGET }).toBeGreaterThan(0);
  expect(Date.now() - t).toBeLessThan(BUDGET);
  const badges = await page.getByTestId("graph").evaluate((e) =>
    (
      e as unknown as {
        cy: { nodes: (s: string) => { map: (f: (n: { data: (k: string) => unknown }) => unknown) => unknown[] } };
      }
    ).cy
      .nodes(".component:childless")
      .map((n) => n.data("impacted")),
  );
  expect(badges.some((b) => typeof b === "number" && b > 0)).toBe(true);
});

test("the minimap pans the view", async ({ page, request }) => {
  const snap = await snapshotOf(request, "large");
  await page.goto(at("large", snap, "graph", "level=component&component=component%3A1"));
  await graphReady(page);
  const pan = () =>
    page
      .getByTestId("graph")
      .evaluate((e) => (e as unknown as { cy: { pan: () => { x: number; y: number } } }).cy.pan());
  const before = await pan();
  const box = await page.getByTestId("minimap").boundingBox();
  if (box === null) throw new Error("no minimap");
  await page.mouse.click(box.x + 5, box.y + 5);
  expect(await pan()).not.toEqual(before);
});
