# Real-pipeline Playwright

Browser tests here hit **Vite → agent-service (:8000) → records-mcp (:8001)**. They never start `e2e/mock-api/server.mjs`. If port 8000 looks like the contract mock (no FastAPI `dependencies` on `/health/live`), startup fails immediately.

## Prerequisites

From the kit root, ensure Python deps and dev secrets exist:

```bash
cd records-mcp && uv sync
cd ../agent-service && uv sync
# Paired RSA keys: records-mcp/secrets/mcp-{signing,verification}-key.pem
# Demo login: agent-service/secrets/demo-sessions.json (reviewer / local-demo)
```

The stack supervisor points the agent at `../records-mcp/secrets/mcp-signing-key.pem` so JWT signing matches MCP verification.

## Canonical command (managed stack)

From `web/`:

```bash
npm run test:e2e:real
```

This runs `playwright test -c playwright.real.config.ts`, which:

1. Starts (or reuses) records-mcp and agent-service. When it starts the agent, it reads `agent-service/.env`; set `MODEL_BACKEND=stub` for deterministic plumbing or configure an explicit real provider.
2. Starts Vite with `VITE_AGENT_API_BASE_URL=http://127.0.0.1:8000`
3. Runs `e2e/real-pipeline/tests/journey-real.spec.ts`

## Bring your own processes

Start services yourself, then verify-only mode:

```bash
# Terminal 1 — records MCP
cd records-mcp
uv run python -m clinician_records --host 127.0.0.1 --port 8001

# Terminal 2 — agent (paired signing key + demo sessions)
cd agent-service
export MCP_SIGNING_KEY_PATH=../records-mcp/secrets/mcp-signing-key.pem
export DEMO_SESSIONS_PATH=secrets/demo-sessions.json
export AGENT_DB_PATH=var/agent/playwright-real.sqlite3
uv run uvicorn clinician_agent.main:app --host 127.0.0.1 --port 8000 --workers 1

# Terminal 3 — Playwright (skip spawning backends)
cd web
REAL_E2E_SKIP_START=1 npm run test:e2e:real
```

The browser uses `reviewer` / `local-demo`, selects P001, and uses an
`as_of` date in 2026 so the synthetic records are visible. For a persistent
local stack with Podman, Jaeger, and the collector, use
`skills/start-clinician-stack/scripts/clinician-stack.sh start` from the kit
root instead.

## Ports

| Variable | Default | Purpose |
|----------|---------|---------|
| `REAL_AGENT_PORT` | `8000` | FastAPI agent (must not be the Node mock) |
| `REAL_MCP_PORT` | `8001` | Streamable HTTP MCP |

Mock-only tests remain `npm run test:e2e` (`playwright.config.ts`).
