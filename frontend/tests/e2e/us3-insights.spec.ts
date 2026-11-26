import { expect, test } from "@playwright/test";

import { at, snapshotOf } from "./helpers";

test("cycles list equals the service and shows the cut", async ({ page, request }) => {
  const snap = await snapshotOf(request, "py-cycles");
  const cycles = (await (
    await request.get(`/api/v1/cycles?repository=py-cycles&snapshot=${encodeURIComponent(snap)}&limit=500`)
  ).json()) as {
    groups: { suggested_cut: { method: string } }[];
  };
  await page.goto(at("py-cycles", snap, "cycles"));
  await expect(page.locator(".cycle-list > li")).toHaveCount(cycles.groups.length);
  await expect(page.getByText("minimum feedback arc set")).toBeVisible();
  await expect(page.getByText("loop/a.py → loop/b.py").first()).toBeVisible();
});

test("hotspots with and without history", async ({ page, request }) => {
  const snap = await snapshotOf(request, "history-app");
  const hot = (await (
    await request.get(`/api/v1/hotspots?repository=history-app&snapshot=${snap}&limit=500`)
  ).json()) as { items: unknown[] };
  await page.goto(at("history-app", snap, "hotspots"));
  await expect(page.locator(".tile")).toHaveCount(hot.items.length);
  await expect(page.locator(".risks tbody tr")).toHaveCount(Math.min(10, hot.items.length));
  const plain = await snapshotOf(request, "py-cycles");
  await page.goto(at("py-cycles", plain, "hotspots"));
  await expect(page.getByText(/history not available/)).toBeVisible();
  await expect(page.locator(".tile")).toHaveCount(0);
});

test("search opens a file in the graph", async ({ page, request }) => {
  const snap = await snapshotOf(request, "py-cycles");
  await page.goto(at("py-cycles", snap, "graph"));
  await page.getByRole("searchbox").fill("loop/a");
  await page.getByRole("button", { name: "loop/a.py" }).click();
  await expect(page).toHaveURL(/node=file%3Aloop%2Fa\.py/);
  await expect(page.getByRole("heading", { name: "loop/a.py" })).toBeVisible();
});
