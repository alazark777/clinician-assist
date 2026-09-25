# Agent developer handoff

Own `agent-service/**`; read [contracts](../skills/build-clinician-mvp/references/contracts.md) and [sources](../skills/build-clinician-mvp/references/sources.md).

Implement `clinician_agent.main:app`, strict HTTP/profile schemas, SQLite migrations, and request-scoped model/MCP adapters. Persist run start before external calls; enforce caller/request-ID/input-hash idempotency and versioned feedback. Never hold transactions across external calls. Mark interrupted runs on restart. Follow contracted active/terminal idempotent replay and run polling. Persist review status/revision separately from retrieval status; enforce both feedback versions atomically.

Resolve opaque UI sessions into patient permissions. Issue audience-bound short-lived signed tokens; hide patient IDs from model arguments. Discover MCP definitions, intersect the explicit registry allowlist, and validate schema fingerprints. Never auto-enable tools.

Inventory then read mandatory baseline categories. Cap six model calls, ten additional record IDs, and 60 seconds; allow five-second attempts and one transient read retry within deadline. Cancel further scheduling on disconnect. Validate evidence, dates/numbers, and patient scope; preserve gaps/conflicts and partial status.

Run these commands from `agent-service/`:

```bash
uv run uvicorn clinician_agent.main:app --host 127.0.0.1 --port 8000 --workers 1
uv run pytest tests
```

Environment names are enumerated in README. `MODEL_BACKEND` selects provider identity (`stub`, `google`, `openai`, `custom`); each real backend requires `MODEL_ID` plus the matching credential env vars (`GOOGLE_API_KEY`, `OPENAI_API_KEY`, or `MODEL_API_KEY` with `MODEL_BASE_URL`). The runtime client is always `AsyncOpenAI` against the resolved compatible base URL. Integrate shared startup telemetry; never log API keys or clinical data.

Test scoped concurrency, limits/retries, empty/outage distinction, DB failure/restart, provenance, and feedback conflicts. Diagnose 409 using canonical input/profile versions; diagnose denied MCP access using issuer/audience/expiry without logging tokens.

Add tools/servers through adapters and reviewed registry entries; prove count/ping without coordinator changes. Submit tester evidence, resolve failures, then obtain human stage acceptance.
