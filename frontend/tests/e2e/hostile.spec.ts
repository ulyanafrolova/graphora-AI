import { expect, type Page, test } from "@playwright/test";

import { at, graphReady, snapshotOf } from "./helpers";

// SC-004: the same strings as tests/unit/hostile.test.tsx and backend/tests/e2e_server.py
const HOSTILE = [
  "<script>alert(1)</script>",
  "<img src=x onerror=alert(1)>",
  "javascript:alert(1)",
  "**md**",
  "[a](javascript:x)",
];
const NAME = "<img src=x onerror=alert(1)>";

test.beforeEach(({ page }) => {
  page.on("dialog", () => {
    throw new Error("a dialog opened");
  });
});

async function nothingInjected(page: Page) {
  await expect(page.locator('img[src="x"], main script, a[href^="javascript:"]')).toHaveCount(0);
}

test("repository, file names and contents are text", async ({ page, request }) => {
  const snap = await snapshotOf(request, NAME);
  await page.goto(at(NAME, snap, "graph", "level=file"));
  await graphReady(page);
  await expect(page.locator("header").getByText(NAME).first()).toBeVisible();
  const labels = await page.getByTestId("graph").evaluate((e) =>
    (
      e as unknown as {
        cy: { nodes: () => { map: (f: (n: { data: (k: string) => string }) => string) => string[] } };
      }
    ).cy
      .nodes()
      .map((n) => n.data("label")),
  );
  expect(labels).toEqual(expect.arrayContaining([`${NAME}.py`, "**md**.py", "javascript:alert(1).py"]));
  await nothingInjected(page);

  await page.goto(at(NAME, snap, "code", "path=app.py"));
  for (const h of HOSTILE) await expect(page.getByText(`# ${h}`, { exact: true })).toBeVisible();
  await nothingInjected(page);

  await page.goto(at(NAME, snap, "code", `path=${encodeURIComponent(`${NAME}.py`)}`));
  await expect(page.getByText(`x = '${NAME}'`, { exact: true })).toBeVisible();
  await nothingInjected(page);
});

test("an agent answer quoting markup is text", async ({ page, request }) => {
  const snap = await snapshotOf(request, "py-cycles");
  await page.goto(at("py-cycles", snap, "ask"));
  await page.getByRole("textbox").fill("What breaks if I change loop/a.py?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByTestId("fact")).toHaveCount(2, { timeout: 30_000 });
  await expect(page.getByTestId("hypothesis")).toContainText(`${NAME}.ts`);
  await nothingInjected(page);
});
