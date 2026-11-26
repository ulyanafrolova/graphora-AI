import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { expect, test } from "@playwright/test";
import { zipSync } from "fflate";

import { graphReady } from "./helpers";

function zipOf(root: string): Buffer {
  const files: Record<string, Uint8Array> = {};
  const walk = (dir: string) => {
    for (const name of readdirSync(dir).sort()) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) walk(path);
      else files[`py-flat/${relative(root, path)}`] = new Uint8Array(readFileSync(path));
    }
  };
  walk(root);
  return Buffer.from(zipSync(files));
}

test("a fresh browser opens on import", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/import$/);
  await expect(page.getByRole("heading", { name: "Import repository" })).toBeVisible();
});

test("zip upload to graph", async ({ page }) => {
  await page.goto("/import");
  await page.getByRole("tab", { name: "ZIP upload" }).click();
  const zip = zipOf(join(import.meta.dirname, "../../../fixtures/repos/py-flat/repo"));
  await page.getByLabel("ZIP archive").setInputFiles({ name: "py-flat.zip", mimeType: "application/zip", buffer: zip });
  await page.getByRole("link", { name: "Open graph" }).click({ timeout: 60_000 });
  await graphReady(page);
  await expect(page).toHaveURL(/\/r\/py-flat\//);
  await expect(page.getByTestId("coverage-row").first()).toHaveCount(0);
});

test("a file that is not a zip fails with its reason", async ({ page }) => {
  await page.goto("/import");
  await page.getByRole("tab", { name: "ZIP upload" }).click();
  await page
    .getByLabel("ZIP archive")
    .setInputFiles({ name: "notes.zip", mimeType: "application/zip", buffer: Buffer.from("not a zip") });
  await expect(page.getByRole("alert")).toContainText(/:/, { timeout: 60_000 });
  await expect(page.getByRole("button", { name: /Try again|Retry/ })).toBeVisible();
});
