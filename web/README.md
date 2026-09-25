# Clinician web starter

**Status:** Stage B React + TypeScript + Vite UI implemented against the agent HTTP contract.

Build React + TypeScript + Vite at localhost:5173. Fetch only the agent HTTP API. Use its authorized patient catalog, generate a draft for the selected patient/context/`as_of`, inspect source excerpts, reload saved profiles, and submit version-bound accept/needs-correction feedback. Display gaps, conflicts, incomplete retrieval, and run ID. Acceptance records demo review; it never changes source records.

Read [contracts](../skills/build-clinician-mvp/references/contracts.md), [sources](../skills/build-clinician-mvp/references/sources.md), and [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md). Own all files under `web/`, including its API client types, browser tests, scripts, and frontend observability. Do not import another component's source or a root shared package.

## Install

```bash
cd web
npm ci
cp .env.example .env
```

Requires Node **24.x** (see `package.json` engines).

## Canonical commands

```bash
npm run dev -- --host 127.0.0.1 --port 5173
npm run build
npm run test:e2e
npm run test:e2e:real
```

Set `VITE_AGENT_API_BASE_URL` (default in `.env.example`: `http://127.0.0.1:8000`); never put credentials in Vite environment variables. API session provisioning belongs to the backend.

`test:e2e` starts the Vite dev server and a **contract mock agent** on port 8000 for isolated browser checks.

`test:e2e:real` runs a separate Playwright config (`playwright.real.config.ts`) against the **real** agent and records MCP (offline stub, paired RSA keys, `agent-service/secrets/demo-sessions.json`). It refuses to run if port 8000 is the Node mock. See [e2e/real-pipeline/README.md](e2e/real-pipeline/README.md) for prerequisites and manual stack commands.

Test the real browser→API→MCP journey, source rendering, feedback/reload, unauthorized access, empty/incomplete results, cancellation, and escaped hostile text. For connection/CORS failures, check API readiness, loopback origin, and API base URL; for 403, check the demo session's patient access. Share only safe run IDs in diagnostics.

Extend through the stable profile schema. New tools/servers belong in backend registration/adapters; count/ping proofs require no UI changes. Hand test evidence to the independent tester, then obtain human stage acceptance.
