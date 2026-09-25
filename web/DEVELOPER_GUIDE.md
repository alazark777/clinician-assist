# Web developer handoff

**Stage B implemented.** Own `web/**`; coordinate HTTP changes with the agent builder. Follow [contracts](../skills/build-clinician-mvp/references/contracts.md) and [sources](../skills/build-clinician-mvp/references/sources.md).

## Implemented surface

- Typed client for `GET /v1/patients`, `POST /v1/profiles`, `GET /v1/profiles/{id}`, `GET /v1/runs/{id}`, `POST /v1/profiles/{id}/feedback`, and demo session routes.
- Demo login (`POST`/`DELETE /v1/demo/session`) with credentialed fetch to the agent API only.
- Request ID reuse for identical `(patient_id, visit_context, as_of)`; explicit restart issues a new ID after interrupted runs.
- 202 polling via `Location` / run route without silently restarting work.
- Version-bound feedback with 409 stale-review handling; reload restores review fields from GET profile.
- Safe text rendering (React text nodes only), in-flight abort on patient switch/cancel, and late-response guards keyed to active patient.
- Safe error mapping for 403/422/409/429/502/503 and network failures; lifecycle logging excludes clinical payloads.

## Layout

| Path | Purpose |
|---|---|
| `src/api/` | HTTP client and contract types |
| `src/components/` | Login, workspace, facts/sources/gaps/feedback UI |
| `src/hooks/useGenerationSession.ts` | Request ID persistence per input fingerprint |
| `e2e/mock-api/server.mjs` | Contract mock for Playwright (not production) |
| `e2e/tests/` | Mock-backed browser journeys |
| `e2e/real-pipeline/` | Real stack supervisor + HTTP→MCP Playwright project |
| `playwright.real.config.ts` | Playwright config for `test:e2e:real` |

## Commands

```bash
npm run dev -- --host 127.0.0.1 --port 5173
npm run build
npm run test:e2e
npm run test:e2e:real
```

Environment: `VITE_AGENT_API_BASE_URL` only; browser configuration is public.

`test:e2e` (mock project) covers selection → generation → sources → feedback → reload, empty inventory, injection escaping, idempotent retry, patient-switch/cancel races, interrupted-run messaging, and stale-feedback errors.

`test:e2e:real` runs one journey against live agent + records MCP with demo credentials from `agent-service/secrets/demo-sessions.json` (`reviewer` / `local-demo`). Details: [e2e/real-pipeline/README.md](e2e/real-pipeline/README.md).

Browser fixtures under `e2e/fixtures/` are synthetic — not evaluation goldens.

Troubleshoot 422 against request schemas, 409 against request/profile versions, 429 against active-run limits, and 502/503 through safe run-ID diagnostics and API readiness.

Submit evidence to the tester, fix defects, then await human stage acceptance through the orchestrator.
