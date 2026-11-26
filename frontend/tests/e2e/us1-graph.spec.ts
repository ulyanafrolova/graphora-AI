import { expect, test } from "@playwright/test";

import { at, graphReady, nodesWith, snapshotOf } from "./helpers";

test("graph, impact and code on py-cycles", async ({ page, request }) => {
  const snap = await snapshotOf(request, "py-cycles");
  await page.goto(at("py-cycles", snap, "graph"));
  await graphReady(page);
  const components = (await (
    await request.get(`/api/v1/components?repository=py-cycles&snapshot=${encodeURIComponent(snap)}`)
  ).json()) as {
    components: { id: string }[];
  };
  await expect(page.getByTestId("graph")).toHaveAttribute("data-nodes", String(components.components.length));

  await page.goto(at("py-cycles", snap, "graph", "level=component&component=component%3A1&node=file%3Aloop%2Fa.py"));
  await graphReady(page);
  await page.getByRole("button", { name: "Impact mode" }).click();
  await expect(page.getByText("Impact mode", { exact: true }).first()).toBeVisible();
  const impact = (await (
    await request.get(
      `/api/v1/impact?repository=py-cycles&snapshot=${encodeURIComponent(snap)}&target=loop/a.py&limit=500`,
    )
  ).json()) as {
    items: { node: string }[];
  };
  await expect.poll(() => nodesWith(page, "impacted")).toEqual(impact.items.map((i) => i.node).sort());

  await page.getByRole("button", { name: "Open code" }).click();
  await page.getByTestId("line-1").click();
  const graph = (await (
    await request.get(`/api/v1/graph?repository=py-cycles&snapshot=${encodeURIComponent(snap)}`)
  ).json()) as {
    edges: { source: string; line: number; extractor: string; snippet_hash: string }[];
  };
  const edge = graph.edges.find((e) => e.source === "file:loop/a.py" && e.line === 1);
  const provenance = page.getByTestId("provenance");
  await expect(provenance).toContainText(`loop/a.py:1@${snap.slice(0, 16)}`);
  await expect(provenance).toContainText(edge?.extractor ?? "missing");
  await expect(provenance).toContainText(edge?.snippet_hash ?? "missing");

  await page.reload();
  await expect(page.getByTestId("provenance")).toContainText(edge?.extractor ?? "missing");
});

test("file level shows externals, hide external removes them", async ({ page, request }) => {
  const snap = await snapshotOf(request, "mixed-fullstack");
  await page.goto(at("mixed-fullstack", snap, "graph", "level=file"));
  await graphReady(page);
  expect((await nodesWith(page, "external")).length).toBeGreaterThan(0);
  await page.getByLabel("Hide external").click();
  await expect(page.getByLabel("Hide external")).toBeChecked();
  await expect.poll(() => nodesWith(page, "external")).toEqual([]);
});
