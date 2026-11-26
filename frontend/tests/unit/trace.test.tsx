import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import answer from "../fixtures/ask-answer.json";

import { claimRows, TraceView } from "@/agents/TraceView";
import type { AskResult } from "@/api/types";

const RESULT = answer as unknown as AskResult;

test("claims from verdicts and hypotheses", () => {
  expect(claimRows(RESULT.trace)).toEqual([
    { cite: "loop/c.py:1@content:485322f43c0d7bd4", status: "verified", reason: null },
    { cite: "user.py:1@content:485322f43c0d7bd4", status: "verified", reason: null },
    { cite: "frontend.ts:1@content:485322f43c0d7bd4", status: "hypothesis", reason: "file_not_in_snapshot" },
  ]);
});

test("timeline, flow, claims and budget", () => {
  render(<TraceView question="What breaks?" result={RESULT} limits={{ tool_calls: 15, revisions: 2 }} />);
  expect(screen.getAllByTestId("trace-row")).toHaveLength(18);
  expect(screen.getByText('dependents({"target":"loop/a.py"})')).toBeInTheDocument();
  expect(screen.getByText("revision 1 of 2: 1 claims")).toHaveClass("revision");
  expect(screen.getByText("request_revision · needs evidence")).toBeInTheDocument();
  expect(screen.getAllByText("verified", { selector: "td .pill" })).toHaveLength(2);
  expect(screen.getByText("hypothesis", { selector: ".pill" })).toBeInTheDocument();
  expect(screen.getByText("1 / 15")).toBeInTheDocument();
  expect(screen.getByText("1 / 2")).toBeInTheDocument();
});
