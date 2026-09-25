# Records-MCP observability

Independent telemetry configuration for **clinician-records-mcp**. The agent API keeps its own copy under `agent-service/observability/` (no root shared package).

## Topology

| Component | Host bind | Purpose |
|---|---|---|
| OTLP HTTP | `127.0.0.1:4328` | SDK export from host process (distinct from agent collector) |
| OTLP gRPC | `127.0.0.1:4327` | Optional gRPC export |
| Jaeger UI | `127.0.0.1:16687` | Trace inspection (loopback only) |

Inside the observability Docker network, services reach the collector at `http://otel-collector:4318` (container port **4318**, not the host-mapped **4328**).

Runtime outputs (gitignored):

- `var/logs/clinician-records-mcp/` — captured stdout, **10 MB × 3** via `scripts/logrotate.conf`
- `var/telemetry/records-jaeger/` — local Jaeger storage; prune with `scripts/prune_telemetry.sh` (default **7** days)

## Start local collection

From `records-mcp/`:

```bash
podman compose -f observability/compose.yaml --env-file observability/images.env up -d
```

When the hardened MCP **application** container is added in Stage B, attach it to network `clinician-records-observability` and set:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

Host-only debugging (`uv run python -m clinician_records ...`) uses `http://127.0.0.1:4328` per `records-mcp/.env.example`.

Validate collector syntax:

```bash
observability/scripts/validate_collector_config.sh
```

## Application integration (records builder)

At MCP process startup:

```python
from clinician_observability import SpanName, configure_telemetry

configure_telemetry()  # defaults: clinician-records-mcp, http://127.0.0.1:4328
tracer = trace.get_tracer(__name__)
```

```bash
cd observability && uv sync --group dev
export PYTHONPATH="${PWD}/lib:${PYTHONPATH}"
```

Environment (see `records-mcp/.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `OTEL_SERVICE_NAME` | `clinician-records-mcp` | Resource attribute |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://127.0.0.1:4328` on host; `http://otel-collector:4318` in compose network | HTTP/protobuf base |
| `APP_ENV` | `local` | `deployment.environment` |

Emit spans `records.list` and `records.read` around tool handlers. Extract W3C `traceparent` from inbound MCP HTTP headers; never derive authorization from trace data or baggage.

Scrub patient IDs, clinical values, record content, tokens, and raw URLs at source. Collector attribute deletion and URL query stripping are defense in depth only.

Register `shutdown_telemetry()` on shutdown. Tool failures must return contracted envelopes even when export is degraded.

### Capture rotated stdout

```bash
mkdir -p ../var/logs/clinician-records-mcp
uv run python -m clinician_records --host 127.0.0.1 --port 8001 2>&1 \
  | tee -a ../var/logs/clinician-records-mcp/app.log
```

### Failure isolation

Telemetry must not affect read-only tool authorization or envelope validation. Bounded queues match the agent stack (`OTEL_BSP_MAX_QUEUE_SIZE`, collector `queue_size: 128`).

## Validation bundled here

```bash
cd observability
uv sync --group dev
uv run pytest
python3 scripts/validate_redaction.py
```

## Acceptance evidence (tester)

Same contract as the agent README, with traces visible at `http://127.0.0.1:16687` and proof that interleaved patient tool calls stay trace-isolated. End-to-end `profile.generate` → `records.read` correlation requires both processes running with propagation implemented in application code.
