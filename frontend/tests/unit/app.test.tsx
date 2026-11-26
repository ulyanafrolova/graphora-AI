import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import { server } from "../setup";

import { App } from "@/App";

test("opens on import when no snapshot was opened before", async () => {
  localStorage.clear();
  server.use(
    http.get("*/api/v1/info", () => HttpResponse.json({ ask: { enabled: false, model: null } })),
    http.get("*/api/v1/repositories", () => HttpResponse.json({ repositories: [] })),
  );
  render(<App />);
  expect(await screen.findByRole("heading", { name: "import" })).toBeInTheDocument();
  expect(await screen.findByText("agents off")).toBeInTheDocument();
});
