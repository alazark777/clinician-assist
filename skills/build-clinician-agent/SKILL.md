---
name: build-clinician-agent
description: Implement the delegated FastAPI agent API and MCP client with bounded retrieval, request-scoped authorization, durable profiles, and a replaceable model adapter.
---

# Build the agent API and MCP client

## Inputs and ownership

Read `../build-clinician-mvp/references/contracts.md` and `../build-clinician-mvp/references/sources.md`, root `AGENTS.md`, and both `agent-service/` handoffs. Consume the assigned stage, explicit registry, published tool schemas, and telemetry interface.

Own `agent-service/**`, including migrations, tests, model/MCP adapters, and telemetry call sites, plus runtime SQLite state under ignored `var/agent/`. Take shared registry, contract, script, and development-fixture assignments from the orchestrator within the authorized implementation scope. Coordinate with other owners before cross-component edits. Keep goldens unavailable to runtime and frozen against tuning; read clinical evidence only through MCP.

## Steps

1. Implement Python 3.12 FastAPI/Pydantic on localhost:8000 with one worker and four active runs; return 429 on overload. Implement all contracted routes, including demo sessions, run polling and health endpoints exactly as contracted. Restrict credentialed CORS to the explicit web origin.
2. Resolve opaque UI sessions into caller and patient permissions. Issue short-lived signed patient-scoped tokens per MCP audience; never forward browser/provider credentials. Keep patient scope out of model arguments and global state. Validate saved-output and feedback authorization.
3. Load `agent-service/config/mcp_servers.json`; discover through the pinned official SDK, intersect explicit tools with allowlists, and verify protocol/schema fingerprints. Qualify tool names, reject unknown arguments and malformed/unsupported envelopes, normalize protocol versus execution errors, and preserve request-scoped credentials on reused connections. Reject arbitrary URLs and newly discovered tools by default.
4. Persist run start before external calls; fail closed on database failure. Enforce request-ID/caller/canonical-input idempotency, conflict on changed input, source snapshots, profile versions, and version-bound feedback. Avoid transactions across external calls. Implement the contracted 202/polling and terminal replay responses. Mark interrupted runs on restart; require a new request ID for explicit restart and never silently resume costly work. Keep saved profiles readable during MCP outage.
5. Inventory then read all available baseline conditions, medications, allergies, latest visit note, relevant labs and vitals selected from inventory keys using the contract’s tie/date rules. Use only successfully read MCP records as evidence. Implement fixed baseline plus one bounded adaptive coordinator through ModelPort, with an offline stub and official OpenAI SDK adapter selected by `MODEL_ID` and an optional OpenAI-compatible base URL.
6. Enforce six model calls, ten additional record IDs excluding baseline, and 60 seconds total. Apply five-second tool attempts and one transient read retry with backoff within the deadline. Never retry denial, schema failure, or bad arguments. Stop scheduling on cancellation/disconnect. Return explicit incomplete verified output or failure without evidence; treat explicit empty inventory as completed retrieval with gaps.
7. Validate the exact profile schema, source existence/scope, numeric/date meaning, fixed `as_of`, future-event exclusion, and recorded-at fallback qualifiers. Preserve uncertainty and conflicting assertions. Treat note instructions as untrusted data; citations also need semantic review. Implement contracted HTTP statuses and draft-to-demo-feedback behavior without source writes.
8. Integrate shared telemetry at startup. Extend only typed adapters, allowlists, and schemas; prove optional count and second-server ping without changing coordinator logic or UI. Route registry edits to its assigned owner.

## Outputs and tests

Deliver service, lockfile, migrations, adapters, updated docs, and command evidence listed in the component guide. Test authorization and interleaved two-patient requests, malformed envelopes, budgets/retries/cancellation, idempotency/concurrency, restart and persistence failure, saved-profile outage access, version conflicts, untrusted text, provenance, and extension isolation through actual HTTP/MCP. Keep fault injection test-only and report stub versus real-model results separately.

## Tester → human gate

Hand command logs, raw outputs/tool traces, and limitations to `verify-clinician-mvp`; repair and retest failures. Obtain human stage acceptance through the orchestrator after independent tester review. Never count skipped model or clinician checks as passed.
