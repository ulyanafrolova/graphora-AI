import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import { server } from "../setup";

import { App } from "@/App";

test("opens on import when no snapshot was opened before", async () => {
  localStorage.clear();
  server.use(
    http.get("*/api/v1/info", () =>
      HttpResponse.json({ ask: { enabled: false, model: null }, jobs: { enabled: false, limits: null } }),
    ),
    http.get("*/api/v1/repositories", () => HttpResponse.json({ repositories: [] })),
  );
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Import repository" })).toBeInTheDocument();
  expect(await screen.findByText("agents off")).toBeInTheDocument();
});

test("import keeps the last snapshot in the header and the menu", async () => {
  localStorage.setItem(
    "graphora.last",
    JSON.stringify({ repository: "py-cycles", snapshot: "content:485322f43c0d7bd4" }),
  );
  window.history.pushState({}, "", "/import");
  server.use(
    http.get("*/api/v1/info", () =>
      HttpResponse.json({ ask: { enabled: false, model: null }, jobs: { enabled: false, limits: null } }),
    ),
    http.get("*/api/v1/repositories", () => HttpResponse.json({ repositories: [] })),
    http.get("*/api/v1/graph", () => HttpResponse.json({ nodes: [], edges: [], coverage: { files: [] } })),
  );
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Import repository" })).toBeInTheDocument();
  expect(screen.getByText("Hotspots").closest("a")).toHaveAttribute(
    "href",
    "/r/py-cycles/content%3A485322f43c0d7bd4/hotspots",
  );
  expect(screen.getByText("Import").closest("a")).toHaveAttribute("aria-current", "page");
  expect(screen.getByText("Dependency graph").closest("a")).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("button", { name: /py-cycles @ content:485322f4/ })).toBeInTheDocument();
});
