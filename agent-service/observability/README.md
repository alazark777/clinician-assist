# Agent-service observability

Independent telemetry configuration for **clinician-agent-api**. The records MCP process keeps its own copy under `records-mcp/observability/` (no root shared package).

## Topology

| Component | Host bind | Purpose |
|---|---|---|
| OTLP HTTP | `127.0.0.1:4318` | SDK export from local API process |
| OTLP gRPC | `127.0.0.1:4317` | Optional gRPC export |
| Jaeger UI | `127.0.0.1:16686` | Trace inspection (loopback only) |
| Collector health | internal `13133` | Container health extension |

Runtime outputs (gitignored):

- `var/logs/clinician-agent-api/` — captured stdout, **10 MB × 3** via `scripts/logrotate.conf`
- `var/telemetry/agent-jaeger/` — local Jaeger storage; prune with `scripts/prune_telemetry.sh` (default **7** days)

## Start local collection

From `agent-service/`:

```bash
podman compose -f observability/compose.yaml --env-file observability/images.env up -d
```

Validate collector syntax (requires Docker/Podman):

```bash
observability/scripts/validate_collector_config.sh
```

## Application integration (agent builder)

Call **once** at process startup before serving traffic:

```python
from clinician_observability import SpanName, configure_telemetry, inject_trace_headers

runtime = configure_telemetry()  # reads OTEL_* and APP_ENV from the environment
tracer = trace.get_tracer(__name__)
```

Add `observability/lib` to `PYTHONPATH` or install the observability project in editable mode:

```bash
cd observability && uv sync --group dev
export PYTHONPATH="${PWD}/lib:${PYTHONPATH}"
```

Environment (see also `agent-service/.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `OTEL_SERVICE_NAME` | `clinician-agent-api` | Resource attribute |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://127.0.0.1:4318` | HTTP/protobuf base URL |
| `APP_ENV` | `local` | `deployment.environment` |
| `OTEL_SDK_DISABLED` | unset | Set `true` to disable export |
| `OTEL_BSP_MAX_QUEUE_SIZE` | `256` | Bounded span queue |
| `OTEL_EXPORTER_OTLP_TIMEOUT` | `5` | Export timeout seconds |

### Required spans and logs

Create spans named exactly: `profile.generate`, `model.call`, `mcp.call`, `profile.validate`, `profile.persist`. MCP client spans should nest under `mcp.call`; the records server emits `records.list` / `records.read`.

For each API→MCP HTTP request, call `inject_trace_headers(headers)` on outbound headers. Do **not** place patient identifiers, clinical values, prompts, tool payloads, tokens, or query-bearing URLs in span attributes, baggage, or logs.

Structured JSON logs go to **stdout** only. Include contract fields (`run_id`, `trace_id`, `span_id`, tool/server names, status/error code, duration, retry count) via logging `extra`. Operational logs must not duplicate SQLite audit payloads.

Metrics: use `runtime.metrics` counters/histograms with **low-cardinality** attributes (`tool_name`, `server_name`, `outcome`) — never `patient_id` or `run_id` labels. Missing provider token usage remains **unknown** (omit or explicit `"unknown"` in API responses, not `0`).

Register `shutdown_telemetry()` on application shutdown.

### Capture rotated stdout

```bash
mkdir -p ../var/logs/clinician-agent-api
uv run uvicorn clinician_agent.main:app --host 127.0.0.1 --port 8000 2>&1 \
  | tee -a ../var/logs/clinician-agent-api/app.log
# Periodically: logrotate -s ../var/logs/agent-logrotate.state observability/scripts/logrotate.conf
```

### Failure isolation

- Exporter/collector outages must **not** block profile persistence or HTTP success paths.
- Bounded queues: SDK `BatchSpanProcessor` + collector/exporter `sending_queue` (`128`).
- Set `OTEL_SDK_DISABLED=true` or stop compose services to simulate outage; API should remain healthy.

## Validation bundled here

```bash
cd observability
uv sync --group dev
uv run pytest
python3 scripts/validate_redaction.py
../observability/scripts/validate_collector_config.sh  # from agent-service/
```

## Acceptance evidence (tester)

Still required at runtime (not proven by config alone):

- One trace linking `profile.generate` → MCP `records.read` in Jaeger (`127.0.0.1:16686`)
- Concurrent patient requests produce isolated trace IDs
- Collector stopped: profiles still persist; logs show `exporter.degraded` / export failures without crashing the API
- Synthetic sentinel scan across logs/spans shows no patient IDs, prompts, tool payloads, or tokens
- Log rotation and `prune_telemetry.sh` retention behavior

SQLite remains authoritative for audit/access events; operational telemetry is supplementary.
