import { defineConfig, devices } from "@playwright/test";

const agentPort = process.env.REAL_AGENT_PORT ?? "8000";

/**
 * Real three-process pipeline: Vite + agent-service + records-mcp.
 * Does not start e2e/mock-api/server.mjs.
 */
export default defineConfig({
  testDir: "./e2e/real-pipeline/tests",
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
      command: "node e2e/real-pipeline/start-stack.mjs",
      url: `http://127.0.0.1:${agentPort}/health/ready`,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      env: {
        ...process.env,
        REAL_AGENT_PORT: agentPort,
        REAL_MCP_PORT: process.env.REAL_MCP_PORT ?? "8001",
      },
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        VITE_AGENT_API_BASE_URL: `http://127.0.0.1:${agentPort}`,
      },
    },
  ],
  projects: [{ name: "real-chromium", use: { ...devices["Desktop Chrome"] } }],
});
