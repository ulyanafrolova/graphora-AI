import type { APIRequestContext, Page } from "@playwright/test";

export async function snapshotOf(request: APIRequestContext, name: string): Promise<string> {
  const body = (await (await request.get("/api/v1/repositories")).json()) as {
    repositories: { name: string; snapshots: string[] }[];
  };
  const found = body.repositories.find((r) => r.name === name);
  if (!found?.snapshots[0]) throw new Error(`not stored: ${name}`);
  return found.snapshots[0];
}

export const at = (repo: string, snap: string, screen: string, query = "") =>
  `/r/${encodeURIComponent(repo)}/${encodeURIComponent(snap)}/${screen}${query ? `?${query}` : ""}`;

export async function graphReady(page: Page) {
  await page.locator('[data-testid="graph"][data-ready="true"]').waitFor();
}

/** Node ids with a class, read from the Cytoscape instance kept on the graph container. */
export async function nodesWith(page: Page, cls: string): Promise<string[]> {
  return page.getByTestId("graph").evaluate(
    (e, c) =>
      (
        e as unknown as { cy: { nodes: (s: string) => { map: (f: (n: { id: () => string }) => string) => string[] } } }
      ).cy
        .nodes(`.${c}`)
        .map((n) => n.id())
        .sort(),
    cls,
  );
}
