import { expect, test } from "@playwright/test";

import { at, snapshotOf } from "./helpers";

test("ask, keep the answer after reload, read its trace", async ({ page, request }) => {
  const snap = await snapshotOf(request, "py-cycles");
  await page.goto(at("py-cycles", snap, "ask"));
  await page.getByRole("textbox").fill("What breaks if I change loop/a.py?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByTestId("fact")).toHaveCount(2, { timeout: 30_000 });
  await expect(page.getByTestId("hypothesis")).toContainText("Not statically proven");
  await expect(page.getByRole("link", { name: "loop/c.py", exact: true })).toBeVisible();

  await page.reload();
  const earlier = page.getByRole("button", { name: "What breaks if I change loop/a.py?" });
  await expect(earlier.first()).toBeVisible();
  await page.getByRole("link", { name: "trace" }).first().click();
  await expect(page.getByRole("heading", { name: "Agent trace" })).toBeVisible();
  await expect(page.getByTestId("trace-row")).toHaveCount(18);
  await expect(page.getByText("1 / 15")).toBeVisible();
});
