import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import type { CycleGroup, Link } from "@/api/types";
import { CutCard } from "@/insights/CutCard";
import { CycleList, cycleTitle } from "@/insights/CycleList";

const link = (s: string, t: string, line = 1): Link =>
  ({ source: `file:${s}`, target: `file:${t}`, confidence: "resolved", type_only: false, via: [],
     edges: [{ source: `file:${s}`, target: `file:${t}`, line, symbol: "hash_pw" }] }) as unknown as Link;

const AUTH: CycleGroup = {
  files: ["file:auth/service.py", "file:users/models.py"],
  cycle: [link("auth/service.py", "users/models.py", 3), link("users/models.py", "auth/service.py", 8)],
  type_only: false,
  confidence: "resolved",
  suggested_cut: { method: "exact", links: [link("users/models.py", "auth/service.py", 8)] },
};
const BILLING: CycleGroup = {
  files: ["file:billing/invoice.py", "file:orders/api.py", "file:pricing.py"],
  cycle: [link("billing/invoice.py", "orders/api.py"), link("orders/api.py", "pricing.py"), link("pricing.py", "billing/invoice.py")],
  type_only: true,
  confidence: "resolved",
  suggested_cut: { method: "greedy", links: [link("pricing.py", "billing/invoice.py")] },
};

test("titles", () => {
  expect(cycleTitle(AUTH)).toBe("auth ⇄ users");
  expect(cycleTitle(BILLING)).toBe("billing → orders → pricing → billing");
  expect(cycleTitle({ ...AUTH, files: ["file:loop/a.py", "file:loop/b.py"] })).toBe("a.py ⇄ b.py");
});

test("list", async () => {
  const select = vi.fn();
  render(<CycleList groups={[AUTH, BILLING]} selected={0} onSelect={select} />);
  const items = screen.getAllByRole("listitem");
  expect(within(items[0] as HTMLElement).getByText("2 edges")).toBeInTheDocument();
  expect(within(items[1] as HTMLElement).getByText("type-only")).toBeInTheDocument();
  expect(items[0]).toHaveAttribute("aria-current", "true");
  await userEvent.click(within(items[1] as HTMLElement).getByRole("button"));
  expect(select).toHaveBeenCalledWith(1);
});

test("cut card", async () => {
  const ask = vi.fn();
  render(<CutCard group={AUTH} lines={new Map([["users/models.py:8", "from ..auth.service import hash_pw"]])} onAsk={ask} />);
  expect(screen.getByText("users/models.py → auth/service.py")).toBeInTheDocument();
  expect(screen.getByText("minimum feedback arc set")).toBeInTheDocument();
  expect(screen.getByText("from ..auth.service import hash_pw")).toBeInTheDocument();
  expect(screen.getByText("Recommendation only — Graphora never modifies your code.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Ask agents about this" }));
  expect(ask).toHaveBeenCalledWith("How do I break the auth ⇄ users cycle?");
  render(<CutCard group={BILLING} lines={new Map()} onAsk={ask} />);
  expect(screen.getByText("greedy (large group)")).toBeInTheDocument();
});

test("empty list", () => {
  render(<CycleList groups={[]} selected={null} onSelect={vi.fn()} />);
  expect(screen.getByText("No cycles in this snapshot.")).toBeInTheDocument();
});
