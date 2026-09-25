# Agent API / MCP client

**Status:** Stage B implementation. The service is independently runnable and tested against the records MCP server.

The service runs Python 3.12 FastAPI/Pydantic at localhost:8000 with one
worker and four active runs. It provides a bounded coordinator, ModelPort with
offline stub/OpenAI-compatible adapters, registry-driven MCP client, and
SQLite under `var/agent/`. It reads clinical evidence exclusively through the
records MCP server and serves the authorized catalog, generation, run polling,
saved profiles, version-bound feedback, and liveness/readiness routes.

Read [contracts](../skills/build-clinician-mvp/references/contracts.md), [sources](../skills/build-clinician-mvp/references/sources.md), and [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md). Own all files under `agent-service/`, including its local API/MCP schemas, configuration, scripts, tests, database, and observability setup. Do not import web/records source, evaluation files, or a root shared package.

Canonical commands from this component directory:

```bash
uv run uvicorn clinician_agent.main:app --host 127.0.0.1 --port 8000 --workers 1
uv run pytest tests
```

The service loads `agent-service/.env` when present. Keep that file local and
ignored; never commit provider keys or signing material.

Environment interface: `MODEL_BACKEND` (`stub`, `google`, `openai`, `custom`), `MODEL_ID`, provider-specific API keys (`GOOGLE_API_KEY`, `OPENAI_API_KEY`, or `MODEL_API_KEY` + `MODEL_BASE_URL` for custom), optional `OPENAI_BASE_URL` when using the OpenAI backend with a non-default gateway, plus `MCP_REGISTRY_PATH`, `MCP_SIGNING_KEY_PATH`, `MCP_TOKEN_ISSUER`, `DEMO_SESSIONS_PATH`, `AGENT_DB_PATH`, `WEB_ORIGIN`, `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `APP_ENV`, and optional test-only `AGENT_TEST_FAULT_FILE`. Keep secret values in ignored local configuration; never forward browser/provider credentials to MCP.

Real providers use the official OpenAI Python SDK (`AsyncOpenAI`) against each
vendor’s OpenAI-compatible HTTP API. For Gemini, set
`MODEL_BACKEND=google`, `MODEL_ID=gemini-3.5-flash-lite` (or another ID your
key supports), and `GOOGLE_API_KEY`; the default Gemini base URL is applied
automatically. For OpenAI, set `MODEL_BACKEND=openai`, `MODEL_ID`, and
`OPENAI_API_KEY`. Some providers reject strict JSON schema; the adapter falls
back to `json_object` when needed.

`MCP_SIGNING_KEY_PATH` must reference an RSA **private** key paired with the records MCP verification key (see `records-mcp/scripts/generate_dev_keys.sh` and `.env.example`). The API no longer auto-generates an unpaired signing key at startup.

Test real HTTP/MCP authorization, interleaved patients, persistence/idempotency, budgets, cancellation, versioned feedback, and outage recovery. Separate stub plumbing evidence from real-model quality. For 503, check database writability and MCP readiness; for 502, check pinned protocol/schema compatibility without downgrading.

Extend via typed adapters and explicit registry allowlists, preserving coordinator/UI code. Submit reproducible results to the tester, then human stage acceptance.
