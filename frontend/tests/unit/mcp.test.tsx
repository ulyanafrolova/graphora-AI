import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import info from "../fixtures/info.json";

import type { Info } from "@/api/types";
import { claudeCommand, cursorConfig, McpView } from "@/integrations/McpPage";
import { NotAvailable } from "@/integrations/NotAvailable";

const TOOLS = (info as unknown as Info).mcp_tools;

test("connection settings name the open snapshot", () => {
  expect(claudeCommand("shop", "content:abc")).toBe(
    "claude mcp add graphora -e GRAPHORA_DATABASE_URL=<database url> -- uv run --directory <graphora>/backend graphora mcp --repository shop --snapshot content:abc",
  );
  expect(JSON.parse(cursorConfig("shop", "content:abc"))).toEqual({
    mcpServers: {
      graphora: {
        command: "uv",
        args: [
          "run",
          "--directory",
          "<graphora>/backend",
          "graphora",
          "mcp",
          "--repository",
          "shop",
          "--snapshot",
          "content:abc",
        ],
        env: { GRAPHORA_DATABASE_URL: "<database url>" },
      },
    },
  });
});

test("tools of the server, read-only, copy buttons", () => {
  const write = vi.fn(() => Promise.resolve());
  Object.assign(navigator, { clipboard: { writeText: write } });
  render(<McpView repository="shop" snapshot="content:abc" tools={TOOLS} />);
  expect(screen.getAllByTestId("mcp-tool").map((r) => r.querySelector("code")?.textContent)).toEqual(
    TOOLS.map((t) => t.name),
  );
  expect(screen.getByText(/read-only/i, { selector: ".label" })).toBeInTheDocument();
  expect(screen.getByText(/stdio/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Copy Claude Code command" }));
  expect(write).toHaveBeenCalledWith(claudeCommand("shop", "content:abc"));
  fireEvent.click(screen.getByRole("button", { name: "Copy Cursor settings" }));
  expect(write).toHaveBeenCalledWith(cursorConfig("shop", "content:abc"));
  expect(screen.queryByText(/%|vs ~/)).toBeNull();
});

test.each([
  ["PR impact", "pr-impact"],
  ["Security", "security"],
])("%s is not available, with no numbers", (title) => {
  const { container } = render(<NotAvailable title={title} />);
  expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
  expect(screen.getByText(/not available in this version/)).toBeInTheDocument();
  expect(container.textContent).not.toMatch(/\d/);
});
