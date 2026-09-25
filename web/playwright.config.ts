import { defineConfig, devices } from "@playwright/test";

const mockPort = process.env.MOCK_AGENT_PORT ?? "8000";

export default defineConfig({
  testDir: "./e2e/tests",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: `node e2e/mock-api/server.mjs`,
      url: `http://127.0.0.1:${mockPort}/health/live`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { MOCK_AGENT_PORT: mockPort },
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        VITE_AGENT_API_BASE_URL: `http://127.0.0.1:${mockPort}`,
      },
    },
  ],
  projects: [{ name: "mock-chromium", use: { ...devices["Desktop Chrome"] } }],
});
