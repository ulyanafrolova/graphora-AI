import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "@/App";

test("opens on import when no snapshot was opened before", async () => {
  localStorage.clear();
  render(<App />);
  expect(await screen.findByText("import")).toBeInTheDocument();
});
