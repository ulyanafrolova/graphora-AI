import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import type { Edge, FileLines } from "@/api/types";
import { CodeView, lineMarkers } from "@/code/CodeView";
import { FileTree, buildTree } from "@/code/FileTree";
import { ProvenancePanel } from "@/code/ProvenancePanel";

const SHA = "a3f9c1e0000000000000000000000000000000000";
const edge = (more: Partial<Edge>): Edge =>
  ({ id: "e", source: "file:api/routes.py", target: "file:auth/service.py", line: 3, column: 1, type: "imports", symbol: "AuthService",
    confidence: "resolved", type_only: false, extractor: "python-adapter@0.1.0", snippet_hash: "sha256:9be1aaaa0c04", form: "static", snapshot: SHA, ...more }) as Edge;

test("tree from coverage files", () => {
  const tree = buildTree([
    { path: "api/routes.py", language: "python", status: "analyzed", flags: [] },
    { path: "api/x.go", language: "go", status: "detected_only", flags: [] },
    { path: "README.md", language: null, status: "not_code", flags: [] },
  ]);
  expect(tree.map((n) => n.name)).toEqual(["api", "README.md"]);
  render(<FileTree files={[{ path: "api/routes.py", language: "python", status: "analyzed", flags: [] }, { path: "api/x.go", language: "go", status: "detected_only", flags: [] }]} selected="api/routes.py" onOpen={vi.fn()} />);
  expect(screen.getByText("x.go")).toHaveClass("detected");
  expect(screen.getByText("routes.py").closest("button")).toHaveAttribute("aria-current", "true");
});

test("markers by edge kind", () => {
  const markers = lineMarkers("api/routes.py", [
    edge({ line: 2, target: "ext:python:fastapi" }),
    edge({ line: 3 }),
    edge({ line: 9, type: "http_call", confidence: "heuristic", target: "file:web/a.ts" }),
    edge({ line: 12, confidence: "unresolved", target: "unresolved:python:x" }),
    edge({ source: "file:other.py", line: 5 }),
  ]);
  expect([...markers.entries()].map(([line, m]) => [line, m.kind])).toEqual([[2, "external"], [3, "resolved"], [9, "http"], [12, "unresolved"]]);
});

const LINES: FileLines = { path: "api/routes.py", has_text: true, line_count: 3, start: 1, end: 3,
  lines: [{ n: 1, text: "# routes" }, { n: 2, text: "from fastapi import x" }, { n: 3, text: "from ..auth.service import AuthService" }] };

test("code lines as text with markers, selecting a line", async () => {
  const select = vi.fn();
  const markers = lineMarkers("api/routes.py", [edge({ line: 3 })]);
  render(<CodeView lines={LINES} markers={markers} selected={3} onSelect={select} />);
  const row = screen.getByTestId("line-3");
  expect(row).toHaveTextContent("3from ..auth.service import AuthService");
  expect(row).toHaveAttribute("aria-current", "true");
  expect(within(row).getByLabelText("resolved import")).toBeInTheDocument();
  await userEvent.click(row);
  expect(select).toHaveBeenCalledWith(3);
});

test("binary and missing files", () => {
  render(<CodeView lines={{ ...LINES, has_text: false, lines: [] }} markers={new Map()} selected={null} onSelect={vi.fn()} />);
  expect(screen.getByText("Binary file: no text to show.")).toBeInTheDocument();
});

test("provenance", () => {
  render(<ProvenancePanel edge={edge({})} />);
  const p = within(screen.getByTestId("provenance"));
  expect(p.getByText("api/routes.py → auth/service.py")).toBeInTheDocument();
  expect(p.getByText("imports · AuthService")).toBeInTheDocument();
  expect(p.getByText("api/routes.py:3@a3f9c1e")).toBeInTheDocument();
  expect(p.getByText("resolved")).toHaveClass("pill");
  expect(p.getByText("python-adapter@0.1.0")).toBeInTheDocument();
  expect(p.getByText("sha256:9be1aaaa0c04")).toBeInTheDocument();
});
