import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, test } from "vitest";

import type { CoverageFile } from "@/api/graph.gen";
import { Header, languageBadges, modelBadge, shortSnapshot } from "@/shell/Header";
import { Sidebar } from "@/shell/Sidebar";
import { DEFAULT } from "@/state/route";

const SHA = "3f1c2b4a5d6e7f8091a2b3c4d5e6f708192a3b4c";
const file = (path: string, language: string | null, status: CoverageFile["status"]): CoverageFile => ({
  path,
  language,
  status,
  flags: [],
});

test("short snapshot ids", () => {
  expect(shortSnapshot(SHA)).toBe("3f1c2b4");
  expect(shortSnapshot("content:485322f43c0d7bd4")).toBe("content:485322f4");
  expect(shortSnapshot(`${SHA}+dirty:0123456789abcdef`)).toBe("3f1c2b4+dirty");
});

test("language badges from coverage", () => {
  const files = [
    file("a.py", "python", "analyzed"),
    file("b.go", "go", "detected_only"),
    file("c.ts", "typescript", "analyzed"),
    file("d.py", "python", "detected_only"),
    file("README.md", null, "not_code"),
  ];
  expect(languageBadges(files)).toEqual([
    { language: "Python", status: "analyzed" },
    { language: "TypeScript", status: "analyzed" },
    { language: "Go", status: "detected only" },
  ]);
});

test("model badge", () => {
  expect(modelBadge({ enabled: true, model: "ollama:qwen3:8b" })).toBe("qwen3:8b · local");
  expect(modelBadge({ enabled: true, model: "openai:gpt-x" })).toBe("gpt-x · openai");
  expect(modelBadge({ enabled: false, model: null })).toBe("agents off");
});

test("header", () => {
  render(
    <Header
      repository="acme/shop"
      snapshot={SHA}
      files={[file("a.py", "python", "analyzed"), file("b.go", "go", "detected_only")]}
      ask={{ enabled: true, model: "ollama:qwen3:8b" }}
    />,
  );
  expect(
    screen.getByText((_, el) => el?.classList.contains("brand") === true && el.textContent === "graphora"),
  ).toBeInTheDocument();
  expect(screen.getByText("acme/shop")).toBeInTheDocument();
  expect(screen.getByText("3f1c2b4")).toBeInTheDocument();
  expect(screen.getByText("Python · analyzed")).toHaveClass("analyzed");
  expect(screen.getByText("Go · detected only")).toHaveClass("detected");
  expect(screen.getByText("qwen3:8b · local")).toBeInTheDocument();
});

test("sidebar sections, items and active item", () => {
  const route = { ...DEFAULT, repository: "r", snapshot: "s", screen: "cycles" as const };
  render(
    <MemoryRouter>
      <Sidebar route={route} current={route.screen} />
    </MemoryRouter>,
  );
  const sections = screen.getAllByRole("navigation")[0] as HTMLElement;
  const text = sections.textContent ?? "";
  for (const label of [
    "Project",
    "Import",
    "Dependency graph",
    "Code & provenance",
    "AI agents",
    "Ask agents",
    "Agent trace",
    "Insights",
    "Cycles",
    "Hotspots",
    "PR impact",
    "Security",
    "Integrations",
    "MCP for agents",
  ]) {
    expect(text).toContain(label);
  }
  expect(within(sections).getByText("Cycles").closest("a")).toHaveAttribute("aria-current", "page");
  expect(within(sections).getByText("Hotspots").closest("a")).toHaveAttribute("href", "/r/r/s/hotspots");
  expect(screen.getByText(/Code is never executed\./)).toBeInTheDocument();
  expect(screen.getByText(/Read-only agents\./)).toBeInTheDocument();
});

test("without a snapshot only import is a link", () => {
  render(
    <MemoryRouter>
      <Sidebar route={null} current={null} />
    </MemoryRouter>,
  );
  expect(screen.getByText("Import").closest("a")).toHaveAttribute("href", "/import");
  expect(screen.getByText("Cycles").closest("a")).toBeNull();
});
