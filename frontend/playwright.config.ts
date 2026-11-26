import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: "http://127.0.0.1:8765", trace: "on-first-retry" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "cd ../backend && uv run python tests/e2e_server.py --port 8765",
    url: "http://127.0.0.1:8765/api/v1/info",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
