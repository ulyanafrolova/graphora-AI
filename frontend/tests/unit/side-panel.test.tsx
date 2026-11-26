import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import type { Answer, Files, Item } from "@/api/types";
import { ComponentPanel } from "@/graph/ComponentPanel";
import { FilePanel } from "@/graph/FilePanel";

const item = (node: string, more: Partial<Item> = {}): Item => ({
  node,
  kind: "file",
  confidence: "resolved",
  type_only: false,
  chain: [],
  ...more,
});

const COMPONENTS = {
  components: [
    { id: "component:1", name: "auth", files: ["file:auth/service.py", "file:auth/tokens.py"], file_count: 2, has_cycle: true },
    { id: "component:2", name: "users", files: ["file:users/models.py"], file_count: 1, has_cycle: false },
    { id: "component:3", name: "api", files: ["file:api/routes.py"], file_count: 1, has_cycle: false },
  ],
  links: [
    { source: "component:1", target: "component:2", imports: 2, heuristic: 0, in_cycle: true },
    { source: "component:2", target: "component:1", imports: 1, heuristic: 0, in_cycle: true },
    { source: "component:3", target: "component:1", imports: 4, heuristic: 1, in_cycle: false },
  ],
} as unknown as Answer;
const KEY_FILES = {
  items: [
    item("file:users/models.py", { transitive_dependents: 9, direct_dependents: 3 }),
    item("file:auth/service.py", { transitive_dependents: 7, direct_dependents: 4 }),
    item("file:auth/tokens.py", { transitive_dependents: 2, direct_dependents: 1 }),
  ],
} as unknown as Answer;
const CYCLES = {
  groups: [
    { files: ["file:auth/service.py", "file:users/models.py"], cycle: [{}, {}], type_only: false, confidence: "resolved" },
  ],
} as unknown as Answer;
const FILES: Files = {
  repository: "r",
  snapshot: "s",
  files: [
    { path: "auth/service.py", has_text: true, line_count: 412 },
    { path: "auth/tokens.py", has_text: true, line_count: 88 },
    { path: "users/models.py", has_text: true, line_count: 50 },
  ],
};

test("component panel", async () => {
  const expand = vi.fn();
  const ask = vi.fn();
  render(
    <ComponentPanel
      component={COMPONENTS.components?.[0] ?? null}
      components={COMPONENTS}
      keyFiles={KEY_FILES}
      cycles={CYCLES}
      files={FILES}
      onExpand={expand}
      onAsk={ask}
      onSelect={vi.fn()}
    />,
  );
  expect(screen.getByRole("heading", { name: "auth" })).toBeInTheDocument();
  expect(screen.getByText("2 files · 500 LOC")).toBeInTheDocument();
  expect(within(screen.getByTestId("depends-on")).getByText("1")).toBeInTheDocument();
  expect(within(screen.getByTestId("used-by")).getByText("2")).toBeInTheDocument();
  expect(within(screen.getByTestId("centrality")).getByText("#2")).toBeInTheDocument();
  const keys = screen.getAllByTestId("key-file").map((li) => li.textContent);
  expect(keys).toEqual(["auth/service.pyin 7", "auth/tokens.pyin 2"]);
  expect(screen.getByText("Cycle with users (2 edges)")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Expand component" }));
  await userEvent.click(screen.getByRole("button", { name: "Ask about auth" }));
  expect(expand).toHaveBeenCalledOnce();
  expect(ask).toHaveBeenCalledWith("Explain the auth component");
});

test("file panel", async () => {
  const toggle = vi.fn();
  const open = vi.fn();
  const select = vi.fn();
  const neighbors = {
    outgoing: [item("file:users/models.py"), item("ext:python:jwt", { kind: "external" })],
    incoming: [item("file:api/routes.py"), item("file:web/login.ts", { confidence: "heuristic" })],
  } as unknown as Answer;
  const hotspots = { items: [item("file:x.py"), item("file:auth/service.py")] } as unknown as Answer;
  render(
    <FilePanel
      node="file:auth/service.py"
      files={FILES}
      keyFiles={KEY_FILES}
      hotspots={hotspots}
      neighbors={neighbors}
      cycles={CYCLES}
      impact={false}
      onToggleImpact={toggle}
      onOpenCode={open}
      onSelect={select}
    />,
  );
  expect(screen.getByRole("heading", { name: "auth/service.py" })).toBeInTheDocument();
  expect(screen.getByText("412 LOC · key file #2 · hotspot #2")).toBeInTheDocument();
  const out = within(screen.getByTestId("dependencies"));
  expect(out.getByText("users/models.py")).toBeInTheDocument();
  expect(out.getByText("external")).toBeInTheDocument();
  const inc = within(screen.getByTestId("dependents"));
  expect(inc.getByText("heuristic")).toBeInTheDocument();
  expect(inc.getAllByText("resolved")).toHaveLength(1);
  expect(screen.getByText("Cycle: auth/service.py ⇄ users/models.py")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Impact mode" }));
  await userEvent.click(screen.getByRole("button", { name: "Open code" }));
  await userEvent.click(out.getByText("users/models.py"));
  expect(toggle).toHaveBeenCalledOnce();
  expect(open).toHaveBeenCalledOnce();
  expect(select).toHaveBeenCalledWith("file:users/models.py");
});

test("impact button shows its state", () => {
  render(
    <FilePanel
      node="file:auth/service.py"
      files={FILES}
      keyFiles={KEY_FILES}
      hotspots={undefined}
      neighbors={undefined}
      cycles={CYCLES}
      impact
      onToggleImpact={vi.fn()}
      onOpenCode={vi.fn()}
      onSelect={vi.fn()}
    />,
  );
  expect(screen.getByRole("button", { name: "Impact mode" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("412 LOC · key file #2")).toBeInTheDocument();
});
