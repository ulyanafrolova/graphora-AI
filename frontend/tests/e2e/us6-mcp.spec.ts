import { expect, test } from "@playwright/test";

import { at, snapshotOf } from "./helpers";

test("the MCP page lists the tools of the service", async ({ page, request }) => {
  const info = (await (await request.get("/api/v1/info")).json()) as { mcp_tools: { name: string }[] };
  const snap = await snapshotOf(request, "py-cycles");
  await page.goto(at("py-cycles", snap, "mcp"));
  await expect(page.getByTestId("mcp-tool").locator("code")).toHaveText(info.mcp_tools.map((t) => t.name));
  await expect(page.getByText(`--repository py-cycles --snapshot ${snap}`).first()).toBeVisible();
});

for (const [screen, title] of [
  ["pr-impact", "PR impact"],
  ["security", "Security"],
] as const) {
  test(`${title} shows the placeholder`, async ({ page, request }) => {
    const snap = await snapshotOf(request, "py-cycles");
    await page.goto(at("py-cycles", snap, screen));
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.getByText("not available in this version", { exact: false })).toBeVisible();
    await expect(page.locator("main canvas")).toHaveCount(0);
  });
}
