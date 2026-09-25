---
name: instrument-clinician-mvp
description: Implement shared backend OpenTelemetry, safe operational logging, local collection, and failure-isolation checks for the delegated clinician MVP build.
---

# Instrument the MVP

## Inputs and ownership

Read `../build-clinician-mvp/references/contracts.md` and `../build-clinician-mvp/references/sources.md`, root `AGENTS.md`, the assigned stage, and component interfaces.

Own `packages/telemetry/**` and `observability/**`, including telemetry tests and `observability/otel-collector.yaml`. Reserve ignored `var/logs/` and `var/telemetry/` for runtime outputs. Give backend/frontend owners precise integration instructions; do not edit their files concurrently. Take shared config, script, contract, and development-fixture assignments from the orchestrator within the authorized implementation scope. Preserve frozen holdout/goldens against tuning.

## Steps

1. Provide one reusable Python setup initialized only at process startup. Use service names `clinician-agent-api` and `clinician-records-mcp`; define `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and `APP_ENV` consistently with component guides. Keep browser tracing optional and frontend logging limited to safe lifecycle failures/run IDs.
2. Instrument `profile.generate`, `model.call`, `mcp.call`, `records.list`, `records.read`, `profile.validate`, and `profile.persist`. Use SDK-supported hooks to inject/extract W3C traceparent for each API→MCP request. Never derive authorization from traces, put patient data in baggage, or forward internal baggage to the model vendor.
3. Emit JSON stdout logs with timestamp, severity, service, environment, event, run_id, trace_id, span_id, tool/server names, status/error code, duration, and retry count. Scrub at source: exclude patient IDs, clinical values, prompts, tool payloads, tokens, credentials, and complete query-bearing URLs. Test automatic SDK/exception attributes as well as custom events.
4. Measure aggregate latency/errors, token counts, tool attempts, timeouts, and budget exhaustion. Avoid patient/run metric labels. Represent missing usage as unknown; show costs unavailable unless a versioned price table exists.
5. Configure local OTLP Collector memory limits, filtering, batching, bounded queues, and a local trace backend. Publish optional container ports on loopback only. Capture stdout per service under ignored `var/logs/` with 10 MB × 3 rotation; store telemetry under ignored `var/telemetry/` with seven-day default retention.
6. Keep observability optional to application success: degrade safely on exporter/collector failure. Have the agent owner implement authoritative access/profile/feedback audit events in SQLite with actor, run, record reference, timestamp, and action; operational logs must not contain clinical payloads.
7. Reuse the same setup and generic server/tool attributes for new tools and servers; do not branch coordinator or UI code by server identity. Coordinate integration and command changes through the orchestrator.

## Outputs and tests

Deliver shared setup, collector/backend configuration, reproducible startup instructions, and integration handoff. Test end-to-end trace correlation and interleaved-request isolation, source-side redaction using synthetic sentinels, bounded exporter failure, collector outage with successful profile persistence, rotation/retention, and low-cardinality metrics. Report unavailable traces or provider usage honestly.

## Tester → human gate

Submit configuration and observed traces/redaction/failure results to `verify-clinician-mvp`. Repair findings, then seek explicit human stage acceptance through the orchestrator after tester review. Do not claim acceptance based only on configuration inspection.
