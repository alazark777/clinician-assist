---
name: build-clinician-records
description: Implement the delegated isolated MCP records server with read-only synthetic patient access, strict schemas, scoped authorization, and extensibility proofs.
---

# Build the records MCP server

## Inputs and ownership

Read `../build-clinician-mvp/references/contracts.md` and `../build-clinician-mvp/references/sources.md`, root `AGENTS.md`, and both `records-mcp/` handoffs. Consume the assigned stage, patient schema, approved registry interface, verification material, and shared telemetry API.

Own `records-mcp/**`, including typed handlers, adapter, Dockerfile, component Compose file, tests, and docs. Integrate telemetry in owned call sites. Take shared registry, contract, script, and development-fixture assignments from the orchestrator within the authorized implementation scope. Coordinate cross-component edits with their owners; preserve frozen holdout/goldens against tuning. Keep runtime patient access read-only.

## Steps

1. Implement official MCP Python SDK 2.x Streamable HTTP at localhost:8001 `/mcp`, targeting protocol 2026-07-28. Verify pinned compatibility against official sources; let the SDK handle serialization/version negotiation and supported context hooks. Report unavailable compatibility rather than silently downgrading or writing JSON-RPC/session machinery.
2. Validate origin and a signed scoped development token independently on every request using an established JWT library with explicit algorithm, issuer, audience, and expiry checks. Receive verification material only. Derive patient scope from verified request context, never model input, baggage, paths supplied by callers, or global state.
3. Register only typed read-only `list_records` and `read_records` with strict input/output schemas. Publish the contract envelopes and SDK structured results/isError conventions. Distinguish `ok`, `empty`, `unavailable`, and `denied`; reserve `empty` for complete empty inventories and enforce atomic exact-ID reads. Include inventory `fact_keys` for selection; use stable retryability/error codes and expose no records on denial.
4. Resolve opaque record IDs through the authorized patient index. Enforce 20 IDs/read, 100 inventory records, and 100 KB/result. Mark oversized inventory incomplete; reject oversized reads/results safely rather than pretending completeness. Preserve schema/dataset versions, source versions, dates, and provenance. Do not load evaluator answers or interpret note text as instructions.
5. Supply hardened container execution: only `/records-mcp/data/patients` mounted read-only, non-root user, read-only root, dropped capabilities, resource limits, tmpfs `/tmp`, and loopback host publishing. Never mount the repository, evals, secrets, or agent database. Supply a Podman-compatible command and a process-only debugging command; the latter does not prove isolation.
6. Add handlers through typed schema + explicit registration + authorized client allowlist + fixtures. Keep optional `get_record_counts` disabled for clinical use; support evaluator proof alongside a second test-only server's `ping`. Preserve the coordinator/UI and route shared registry changes through its owner.

## Outputs and tests

Deliver the server, pinned dependencies/image, container definitions, updated docs, and demonstrated canonical commands. Test real SDK discovery/invocation, all envelopes, unknown fields, invalid/expired/wrong-audience tokens, interleaved patients, opaque-ID traversal, limits, missing/malformed records, incomplete inventory, and error normalization. Prove mount isolation by inspecting the running container and failed accesses/writes, including evaluator/database absence. Verify trace propagation without patient baggage.

## Tester → human gate

Submit contract and isolation evidence to `verify-clinician-mvp`; repair failures and retest. Return to the orchestrator for explicit human stage acceptance after tester review. Label process-only or mocked checks insufficient for container acceptance.
