import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { expect, test } from "vitest";

import { server } from "../setup";
import info from "../fixtures/info.json";

import { makeQueryClient } from "@/api/queries";
import { ImportPage } from "@/import/ImportPage";

const job = (stage: string, more: object = {}) => ({
  id: "j1", stage, source: { kind: "github", repository: "github.com/o/r", ref: null }, limits: {}, result: null, error: null, ...more,
});
const DONE = job("done", { result: { action: "stored", repository: "github.com/o/r", snapshot: "3f1c2b4a5d6e7f8091a2b3c4d5e6f708192a3b4c", files: 3, edges: 2, unresolved: 0, warnings: [] } });

function show() {
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter>
        <ImportPage poll={5} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function overview() {
  return http.get("*/api/v1/overview", () =>
    HttpResponse.json({ snapshot: "x", languages: { python: 2, go: 1 }, files: { analyzed: 2, detected_only: 1, not_code: 1, skipped: 0 } }),
  );
}

test("github import follows the stages to done", async () => {
  let body: unknown = null;
  const stages = ["queued", "resolving", "fetching", "analyzing", "storing"];
  server.use(
    http.get("*/api/v1/info", () => HttpResponse.json(info)),
    http.post("*/api/v1/jobs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(job("queued"), { status: 202 });
    }),
    http.get("*/api/v1/jobs/j1", () => HttpResponse.json(stages.length ? job(stages.shift() ?? "") : DONE)),
    http.get("*/api/v1/graph", () =>
      HttpResponse.json({ coverage: { files: [
        { path: "a.py", language: "python", status: "analyzed", flags: [] },
        { path: "b.py", language: "python", status: "analyzed", flags: [] },
        { path: "c.go", language: "go", status: "detected_only", flags: [] },
        { path: "README.md", language: null, status: "not_code", flags: [] },
      ] } }),
    ),
    overview(),
  );
  show();
  expect(await screen.findByText("never — static analysis only")).toBeInTheDocument();
  expect(screen.getByText("5 000")).toBeInTheDocument();
  expect(screen.getByText(/node_modules/)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("GitHub URL"), "https://github.com/o/r");
  await userEvent.type(screen.getByLabelText("Branch, tag or commit"), "main");
  await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
  expect(await screen.findByText("3f1c2b4", {}, { timeout: 3000 })).toBeInTheDocument();
  expect(body).toEqual({ github: "https://github.com/o/r", ref: "main" });
  expect(screen.getByRole("link", { name: "Open graph" })).toHaveAttribute("href", "/r/github.com%2Fo%2Fr/3f1c2b4a5d6e7f8091a2b3c4d5e6f708192a3b4c/graph");
  const rows = screen.getAllByTestId("coverage-row").map((r) => r.textContent);
  expect(rows).toEqual(["Python2full", "Go1detected only", "Other1not code"]);
});

test("zip upload and a failed job", async () => {
  let name = "";
  server.use(
    http.get("*/api/v1/info", () => HttpResponse.json(info)),
    http.post("*/api/v1/jobs/zip", ({ request }) => {
      name = new URL(request.url).searchParams.get("name") ?? "";
      return HttpResponse.json(job("queued"), { status: 202 });
    }),
    http.get("*/api/v1/jobs/j1", () => HttpResponse.json(job("failed", { error: { kind: "limit", message: "file limit exceeded" } }))),
  );
  show();
  await userEvent.click(await screen.findByRole("tab", { name: "ZIP upload" }));
  await userEvent.upload(screen.getByLabelText("ZIP archive"), new File([new Uint8Array(4)], "app.zip", { type: "application/zip" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("limit: file limit exceeded");
  expect(name).toBe("app.zip");
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
});

test("a reused analysis is done at once", async () => {
  server.use(
    http.get("*/api/v1/info", () => HttpResponse.json(info)),
    http.post("*/api/v1/jobs", () => HttpResponse.json(DONE, { status: 202 })),
    http.get("*/api/v1/graph", () => HttpResponse.json({ coverage: { files: [] } })),
    overview(),
  );
  show();
  await userEvent.type(await screen.findByLabelText("GitHub URL"), "https://github.com/o/r");
  await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
  expect(await screen.findByRole("link", { name: "Open graph" })).toBeInTheDocument();
  expect(screen.queryByTestId("stages")).toBeNull();
});

test("too many jobs and no job runner", async () => {
  server.use(
    http.get("*/api/v1/info", () => HttpResponse.json({ ...info, jobs: { enabled: false, limits: null } })),
  );
  show();
  expect(await screen.findByText("Analysis jobs are off in this service.")).toBeInTheDocument();
  expect(screen.queryByText("5 000")).toBeNull();
});
