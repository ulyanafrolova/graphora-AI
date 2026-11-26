import { readFileSync } from "node:fs";

import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { expect, test } from "vitest";

import answer from "../fixtures/ask-answer.json";
import { server } from "../setup";

import { AnswerCard } from "@/agents/AnswerCard";
import { AskPage } from "@/agents/AskPage";
import { clearRuns, openHistory } from "@/agents/history";
import { makeQueryClient } from "@/api/queries";
import type { AskResult } from "@/api/types";
import { DEFAULT } from "@/state/route";

const SNAP = "content:485322f43c0d7bd4";
const route = { ...DEFAULT, repository: "py-cycles", snapshot: SNAP, screen: "ask" as const };

test("answer card: facts with citations, hypothesis apart, text as text", () => {
  render(
    <MemoryRouter>
      <AnswerCard result={answer as unknown as AskResult} route={route} model="scripted:e2e" />
    </MemoryRouter>,
  );
  const facts = screen.getAllByTestId("fact");
  expect(facts).toHaveLength(2);
  expect(within(facts[0] as HTMLElement).getByRole("link", { name: "loop/c.py:1" })).toHaveAttribute(
    "href",
    `/r/py-cycles/${encodeURIComponent(SNAP)}/code?path=loop%2Fc.py&line=1`,
  );
  expect(screen.getByTestId("hypothesis")).toHaveTextContent(
    "Hypothesis — `frontend.ts` imports `loop/a.py`. Not statically proven.",
  );
  expect(screen.getByText("Changing loop/a.py breaks loop/c.py and user.py.")).toBeInTheDocument();
  expect(screen.getByText("1 tool calls · 1 revisions · scripted:e2e")).toBeInTheDocument();
});

test("ask streams steps, shows the answer and keeps it in history", async () => {
  const h = await openHistory();
  await clearRuns(h, "py-cycles", SNAP);
  server.use(
    http.get("*/api/v1/info", () =>
      HttpResponse.json({
        ask: { enabled: true, model: "scripted:e2e" },
        jobs: { enabled: false, limits: null },
        mcp_tools: [],
      }),
    ),
    http.post(
      "*/api/v1/ask",
      () =>
        new HttpResponse(readFileSync("tests/fixtures/ask.sse"), { headers: { "Content-Type": "text/event-stream" } }),
    ),
  );
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter>
        <AskPage route={route} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await userEvent.type(screen.getByRole("textbox"), "What breaks if I change loop/a.py?");
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  expect(await screen.findAllByTestId("fact")).toHaveLength(2);
  expect(await screen.findByRole("button", { name: /What breaks if I change loop\/a.py\?/ })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Clear history" }));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: /What breaks if I change loop\/a.py\?/ })).toBeNull(),
  );
});

test("busy is shown with retry", async () => {
  server.use(
    http.get("*/api/v1/info", () =>
      HttpResponse.json({
        ask: { enabled: true, model: "x:y" },
        jobs: { enabled: false, limits: null },
        mcp_tools: [],
      }),
    ),
    http.post("*/api/v1/ask", () =>
      HttpResponse.json(
        { error: { kind: "busy", message: "busy" } },
        { status: 429, headers: { "Retry-After": "30" } },
      ),
    ),
  );
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter>
        <AskPage route={route} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Which files depend on the most-used file?" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Another question is being answered");
});
