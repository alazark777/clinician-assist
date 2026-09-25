/**
 * Supervises records-mcp (:8001) and agent-service (:8000) for real-pipeline Playwright.
 * Exits non-zero on startup failure; never starts the contract mock.
 */

import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { assertMcpPort, assertRealAgent } from "./agent-probe.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = path.resolve(__dirname, "../..");
const KIT_ROOT = path.resolve(WEB_ROOT, "..");
const RECORDS_DIR = path.join(KIT_ROOT, "records-mcp");
const AGENT_DIR = path.join(KIT_ROOT, "agent-service");

const AGENT_PORT = Number(process.env.REAL_AGENT_PORT ?? 8000);
const MCP_PORT = Number(process.env.REAL_MCP_PORT ?? 8001);
const AGENT_BASE = `http://127.0.0.1:${AGENT_PORT}`;
const MCP_BASE = `http://127.0.0.1:${MCP_PORT}`;

/** @type {import("node:child_process").ChildProcess[]} */
const managed = [];

function log(message) {
  process.stderr.write(`[real-pipeline] ${message}\n`);
}

function fail(message) {
  log(`ERROR: ${message}`);
  shutdown(1);
}

/** Parse agent-service/.env (last duplicate key wins). */
function loadAgentDotenv() {
  const envPath = path.join(AGENT_DIR, ".env");
  if (!existsSync(envPath)) {
    return {};
  }
  /** @type {Record<string, string>} */
  const parsed = {};
  for (const rawLine of readFileSync(envPath, "utf8").split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const eq = line.indexOf("=");
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim();
    if (key) parsed[key] = value;
  }
  return parsed;
}

function requirePath(label, filePath) {
  if (!existsSync(filePath)) {
    fail(`${label} missing at ${filePath}. Generate dev keys and demo sessions per kit READMEs.`);
  }
}

async function waitFor(fn, { timeoutMs, intervalMs, label }) {
  const deadline = Date.now() + timeoutMs;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      await fn();
      return;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
      await new Promise((r) => setTimeout(r, intervalMs));
    }
  }
  fail(`${label} timed out after ${timeoutMs}ms: ${lastError}`);
}

function spawnManaged(label, command, args, options) {
  const child = spawn(command, args, {
    ...options,
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout?.on("data", (chunk) => {
    process.stderr.write(`[${label}] ${chunk}`);
  });
  child.stderr?.on("data", (chunk) => {
    process.stderr.write(`[${label}] ${chunk}`);
  });
  child.on("exit", (code, signal) => {
    if (!shuttingDown) {
      fail(`${label} exited unexpectedly (code=${code ?? "null"}, signal=${signal ?? "null"})`);
    }
  });
  managed.push(child);
  return child;
}

let shuttingDown = false;

function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const child of managed) {
    child.kill("SIGTERM");
  }
  setTimeout(() => process.exit(code), 250);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

async function servicesAlreadyUp() {
  try {
    await assertRealAgent(AGENT_BASE);
    await assertMcpPort(MCP_BASE);
    return true;
  } catch (err) {
    if (err instanceof Error && err.message.includes("contract mock")) {
      throw err;
    }
    return false;
  }
}

async function main() {
  requirePath(
    "MCP verification key",
    path.join(RECORDS_DIR, "secrets/mcp-verification-key.pem"),
  );
  requirePath(
    "MCP signing key (records-mcp)",
    path.join(RECORDS_DIR, "secrets/mcp-signing-key.pem"),
  );
  requirePath(
    "Demo sessions",
    path.join(AGENT_DIR, "secrets/demo-sessions.json"),
  );

  if (process.env.REAL_E2E_SKIP_START === "1") {
    log(`REAL_E2E_SKIP_START=1 — verifying only (${AGENT_BASE}, ${MCP_BASE})`);
    await assertRealAgent(AGENT_BASE);
    await assertMcpPort(MCP_BASE);
    log("External stack verified.");
    await new Promise(() => {});
    return;
  }

  if (await servicesAlreadyUp()) {
    log(`Reusing existing agent (${AGENT_BASE}) and records MCP (${MCP_BASE}).`);
    await new Promise(() => {});
    return;
  }

  const agentDotenv = loadAgentDotenv();
  const modelBackend = agentDotenv.MODEL_BACKEND ?? process.env.MODEL_BACKEND ?? "stub";
  log(`Starting records-mcp and agent-service (MODEL_BACKEND=${modelBackend}, paired RSA keys)…`);

  const recordsEnv = {
    ...process.env,
    PATIENT_DATA_DIR: "data/patients",
    MCP_VERIFICATION_KEY_PATH: "secrets/mcp-verification-key.pem",
    MCP_TOKEN_ISSUER: "clinician-agent-api",
    MCP_TOKEN_AUDIENCE: "clinician-records-mcp",
    MCP_ALLOWED_ORIGINS: `http://127.0.0.1:${AGENT_PORT}`,
    APP_ENV: "local",
  };
  delete recordsEnv.OTEL_EXPORTER_OTLP_ENDPOINT;

  spawnManaged(
    "records-mcp",
    "uv",
    ["run", "python", "-m", "clinician_records", "--host", "127.0.0.1", "--port", String(MCP_PORT)],
    { cwd: RECORDS_DIR, env: recordsEnv },
  );

  await waitFor(() => assertMcpPort(MCP_BASE), {
    timeoutMs: 90_000,
    intervalMs: 500,
    label: "records-mcp",
  });

  const agentEnv = {
    ...process.env,
    ...agentDotenv,
    MCP_REGISTRY_PATH: "config/mcp_servers.json",
    MCP_SIGNING_KEY_PATH: path.join("..", "records-mcp", "secrets", "mcp-signing-key.pem"),
    MCP_TOKEN_ISSUER: "clinician-agent-api",
    MCP_REQUEST_ORIGIN: AGENT_BASE,
    DEMO_SESSIONS_PATH: "secrets/demo-sessions.json",
    AGENT_DB_PATH: "var/agent/playwright-real.sqlite3",
    WEB_ORIGIN: "http://127.0.0.1:5173",
    APP_ENV: "local",
  };
  delete agentEnv.OTEL_EXPORTER_OTLP_ENDPOINT;

  spawnManaged(
    "agent-service",
    "uv",
    [
      "run",
      "uvicorn",
      "clinician_agent.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(AGENT_PORT),
      "--workers",
      "1",
    ],
    { cwd: AGENT_DIR, env: agentEnv },
  );

  await waitFor(() => assertRealAgent(AGENT_BASE), {
    timeoutMs: 120_000,
    intervalMs: 500,
    label: "agent-service",
  });

  log(`Stack ready: agent ${AGENT_BASE}, records MCP ${MCP_BASE}/mcp`);
  await new Promise(() => {});
}

main().catch((err) => {
  fail(err instanceof Error ? err.message : String(err));
});
