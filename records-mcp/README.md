# Records MCP server

**Status:** Stage B implementation for the isolated records MCP server
(Streamable HTTP, JWT scope, list/read tools, tests, and hardened compose).

Run the separate official MCP Python SDK 2.x Streamable HTTP server on
localhost:8001 `/mcp`, targeting protocol 2026-07-28. It alone reads the
component-owned `data/patients/*.json`. Expose explicitly registered
`list_records` and `read_records`; derive patient scope from each verified
signed token.

Read [contracts](../skills/build-clinician-mvp/references/contracts.md), [sources](../skills/build-clinician-mvp/references/sources.md), and [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md). Own all files under `records-mcp/`, including its local MCP schemas, patient data, scripts, tests, container configuration, and observability setup. Do not import agent/web source, evaluation files, or a root shared package.

Canonical commands from this component directory:

```bash
podman compose -f compose.yaml up --build -d
uv run python -m clinician_records --host 127.0.0.1 --port 8001
uv run pytest tests
```

Podman is the supported container engine. On macOS, start the VM with
`podman machine start` and install a compose provider with
`brew install podman-compose`. The repository-root startup script uses Podman
for Jaeger/OTel and runs this MCP service as a separate host process for the
normal local UI workflow. Use `podman compose -f compose.yaml up --build -d`
when proving hardened container isolation. The isolation test skips only when
no usable Podman service is available. Process-only startup does not establish
container isolation.

Environment interface: `PATIENT_DATA_DIR`, `MCP_VERIFICATION_KEY`, `MCP_TOKEN_ISSUER`, `MCP_TOKEN_AUDIENCE`, `MCP_ALLOWED_ORIGINS`, `MCP_REQUEST_STATE_KEY` (optional shared request-state key), `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `APP_ENV`, `ENABLE_EXTENSION_TOOLS` (test-only `get_record_counts`). Supply verification material only; never signing/provider secrets. Generate local key pairs with `scripts/generate_dev_keys.sh`.

Pinned stack: Python 3.12, `mcp==2.2.0` (MCPServer + Streamable HTTP, protocol negotiation via SDK), JWT RS256 verification with explicit issuer/audience/expiry checks.

Test SDK discovery, envelopes, authorization, two-patient interleaving, limits, traversal, and container isolation. For unavailable records, check the read-only mount; for denied requests, check audience/issuer/expiry; for protocol mismatch, report pinned compatibility failure.

Add typed handlers, schemas, explicit registration, reviewed client allowlists, and fixtures. Keep optional counts disabled clinically; prove extensions without coordinator/UI edits. Submit tester evidence, then human stage acceptance.
