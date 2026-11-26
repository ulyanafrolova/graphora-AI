import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { expect, test, vi } from "vitest";

import { ApiError } from "@/api/client";
import { ErrorState } from "@/shell/ErrorState";
import { Legend, LEGEND } from "@/shell/Legend";

function show(error: ApiError, retry = vi.fn()) {
  render(
    <MemoryRouter>
      <ErrorState error={error} onRetry={retry} />
    </MemoryRouter>,
  );
  return retry;
}

test.each([
  [new ApiError(0, "network", "x"), "Graphora service unavailable", "Retry"],
  [new ApiError(503, "store_unavailable", "x"), "Graphora service unavailable", "Retry"],
  [new ApiError(404, "not_found", "snapshot not found: r s"), "Snapshot not found", "Import"],
  [new ApiError(409, "stale", "x"), "Analyzed with an older version — analyze again", "Import"],
  [new ApiError(429, "busy", "x", 30), "Another question is being answered", "Retry"],
  [new ApiError(503, "model_unavailable", "x"), "Model not available", "Retry"],
  [new ApiError(429, "too_many_jobs", "x"), "Too many analyses queued, try later", "Retry"],
  [new ApiError(500, "internal", "x"), "Something went wrong", "Retry"],
])("%s", (error, title, action) => {
  show(error);
  expect(screen.getByRole("alert")).toHaveTextContent(title);
  expect(screen.getByRole(action === "Import" ? "link" : "button", { name: action })).toBeInTheDocument();
});

test("retry calls back", async () => {
  const retry = show(new ApiError(0, "network", "x"));
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(retry).toHaveBeenCalledOnce();
});

test("the service message is shown as text", () => {
  show(new ApiError(404, "not_found", "<b>snapshot not found</b>"));
  expect(screen.getByText("<b>snapshot not found</b>")).toBeInTheDocument();
});

test("busy says when to retry, model unavailable says how to start ollama", () => {
  show(new ApiError(429, "busy", "x", 30));
  expect(screen.getByRole("alert")).toHaveTextContent("try again in 30 s");
});

test("model unavailable explains ollama", () => {
  show(new ApiError(503, "model_unavailable", "connection refused"));
  expect(screen.getByRole("alert")).toHaveTextContent("ollama serve");
});

test("legend rows", () => {
  render(<Legend />);
  for (const row of LEGEND) expect(screen.getByText(row.label)).toBeInTheDocument();
  expect(LEGEND.map((r) => r.key)).toEqual([
    "resolved",
    "heuristic",
    "unresolved",
    "cycle",
    "impact",
    "hypothesis",
    "verified",
    "external",
  ]);
});

test("legend subset", () => {
  render(<Legend only={["heuristic", "cycle"]} />);
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
});
