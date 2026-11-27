import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";

import { server } from "../setup";

import { makeQueryClient } from "@/api/queries";
import type { GraphDocument } from "@/api/types";
import { matchFiles, Search } from "@/graph/Search";

const GRAPH = {
  nodes: ["src/Auth.py", "src/auth_util.py", "lib/x.py"].map((p) => ({ id: `file:${p}`, kind: "file", path: p })),
} as unknown as GraphDocument;

test("file matches are case-insensitive and sorted", () => {
  expect(matchFiles(GRAPH, "AUTH")).toEqual(["file:src/Auth.py", "file:src/auth_util.py"]);
  expect(matchFiles(GRAPH, "")).toEqual([]);
});

test("files and definitions; choosing selects the file", async () => {
  server.use(
    http.get("*/api/v1/definitions", ({ request }) =>
      HttpResponse.json(
        new URL(request.url).searchParams.get("name") === "Auth"
          ? {
              definitions: [{ file: "file:src/Auth.py", path: "src/Auth.py", line: 3, kind: "class", name: "Auth" }],
              total: 1,
            }
          : { definitions: [], total: 0 },
      ),
    ),
  );
  const pick = vi.fn();
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <Search snapshot={{ repository: "r", snapshot: "s" }} graph={GRAPH} onPick={pick} />
    </QueryClientProvider>,
  );
  await userEvent.type(screen.getByRole("searchbox"), "Auth");
  expect(await screen.findByRole("button", { name: "src/Auth.py:3 · class Auth" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "src/auth_util.py" }));
  expect(pick).toHaveBeenCalledWith("file:src/auth_util.py");
  await userEvent.clear(screen.getByRole("searchbox"));
  await userEvent.type(screen.getByRole("searchbox"), "Nope");
  expect(await screen.findByText("no definitions")).toBeInTheDocument();
});
