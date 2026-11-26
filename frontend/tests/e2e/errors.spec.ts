import { expect, test } from "@playwright/test";

import { at, snapshotOf } from "./helpers";

test("service stopped: unavailable, then Retry recovers", async ({ page, request }) => {
  const snap = await snapshotOf(request, "py-cycles");
  await page.route("**/api/v1/**", (route) => route.abort());
  await page.goto(at("py-cycles", snap, "graph"));
  await expect(page.getByText("Graphora service unavailable").first()).toBeVisible();
  await page.unroute("**/api/v1/**");
  await page.getByRole("button", { name: "Retry" }).first().click();
  await expect(page.getByText("Graphora service unavailable")).toHaveCount(0);
  await expect(page.getByTestId("graph")).toBeVisible();
});

test("unknown snapshot address", async ({ page }) => {
  await page.goto(at("py-cycles", "content:0000000000000000", "graph"));
  await expect(page.getByText("Snapshot not found").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Import" }).first()).toBeVisible();
});

test("an analysis of an older version asks to analyze again", async ({ page, request }) => {
  const snap = await snapshotOf(request, "stale-app");
  await page.goto(at("stale-app", snap, "graph"));
  await expect(page.getByText("analyze again").first()).toBeVisible();
});
