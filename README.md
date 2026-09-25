# Clinician assistant implementation kit

This package contains component handoff specifications, synthetic fixtures, a static checker/evaluation starter, and source copies of the coding skills installed separately under `~/.cursor/skills`. **It contains no implemented application.** Component source code, container isolation, model integration, and runtime acceptance remain Stage B deliverables. Kit validation is not application or clinical validation.

The authoritative current specification is [contracts.md](skills/build-clinician-mvp/references/contracts.md), supported by [sources.md](skills/build-clinician-mvp/references/sources.md). The retained v0.1 draft is historical: **the current MCP-in-MVP override requires a separate MCP records server and container isolation now**, despite v0.1 deferring them.

## Stage A dependency compatibility (verified 2026-09-25)

- PyPI serves non-yanked `mcp==2.2.0` (uploaded 2026-09-07, Python >=3.10). Official v2 documentation lists `2026-07-28` in `MODERN_PROTOCOL_VERSIONS` and as `LATEST_PROTOCOL_VERSION`, and the official v2.0.0 release identifies v2 as stable with support for that revision.
- The official [MCP Python SDK v2.2.0 release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.2.0) is available and is the release pinned by both backend lockfiles.
- The backend locks target Python 3.12, as required by the contract. Independent lock checks passed with Python 3.12.12; Stage B must still prove runtime behavior.
- The frontend lock uses the exact registry versions resolved in `web/package-lock.json`. Runtime/browser compatibility is deferred to Stage B.
- Container image digests are not justified until the Stage B container definition exists; none are claimed or pinned in Stage A.

## Architecture and scope

The three-process path is **React/TypeScript/Vite web (localhost:5173) → FastAPI agent HTTP API/MCP client (localhost:8000) → MCP records server (localhost:8001 `/mcp`)**. Web and API run locally; records run in a hardened Docker/Podman-compatible container. Only records MCP reads patient files, through a read-only patient-directory mount. Never mount the repository, evals, secrets, or agent database into that container.

The API owns one bounded runtime clinical coordinator, a scripted offline ModelPort and an OpenAI-compatible adapter configurable for multiple providers, request-scoped patient authorization, and SQLite run/profile/source-snapshot/feedback state under `var/agent/`. Multiple delegated **coding** agents do not imply multiple clinical runtime agents. Reusable backend telemetry sends scrubbed events through a local Collector; SQLite remains authoritative even when telemetry fails.

Generate synthetic outpatient diabetes pre-visit drafts with source-linked facts, gaps, explicit uncertainty, and unresolved conflicts. Do not diagnose, prescribe, order, or write source records. Demo acceptance records version-bound reviewer feedback; it does not establish clinical readiness.

## Use in a coding agent

Open this repository as the coding workspace and ask the agent to read the installed skill plus this repository's source references. For example:

> Read `~/.cursor/skills/build-clinician-mvp/SKILL.md`, `evaluation/AGENTS.md`, and `skills/build-clinician-mvp/references/`. Begin Stage A of the clinician MVP implementation. Present test evidence for human acceptance before advancing stages.

The orchestrator assigns these specialists:

| Skill | Responsibility |
|---|---|
| `build-clinician-web` | Web UI and browser journeys |
| `build-clinician-agent` | Agent HTTP API, model/MCP adapters, SQLite |
| `build-clinician-records` | Read-only MCP tools and container isolation |
| `instrument-clinician-mvp` | Shared telemetry and local collection |
| `verify-clinician-mvp` | Independent evaluation and acceptance evidence |

Read the [web](web/README.md), [agent](agent-service/README.md), and [records](records-mcp/README.md) starters and their developer guides. Each directory is an independent runtime boundary with its own manifest and lock. Run every component command from that component's directory.

## Independent local processes

After implementation, run each component in its own terminal from its component directory:

```bash
# Terminal 1
cd web
npm run dev -- --host 127.0.0.1 --port 5173

# Terminal 2
cd agent-service
uv run uvicorn clinician_agent.main:app --host 127.0.0.1 --port 8000 --workers 1

# Terminal 3
cd records-mcp
docker compose -f compose.yaml up --build
```

The web process talks only to the agent API. The agent process talks to the records MCP endpoint. The records process alone reads its local `data/patients/` directory, and its container receives only that directory as a read-only mount. Use the process-only MCP command in `records-mcp/README.md` only for debugging; it does not establish container isolation.

## Ownership boundaries

The root contains documentation, source skill material, and evaluation assets, but no runtime package or shared dependency manifest. The runtime boundaries are independent:

- `web/` owns the frontend, browser tests, API client types, and frontend diagnostics.
- `agent-service/` owns the HTTP API, MCP client, model adapters, database, local schemas, backend diagnostics, and backend scripts.
- `records-mcp/` owns the MCP server, patient data, MCP schemas, container files, server diagnostics, and server scripts.
- `evaluation/` is an independent test project. It owns scenarios, graders, holdout cases, and evaluation-only scripts. It is never imported or mounted by a runtime service.

The three runtime components intentionally keep local copies of boundary schemas instead of importing a root `shared` package. Compatibility is tested over HTTP and MCP boundaries.

Stage A locks contracts and verifies fixtures/dependencies. Stage B builds three processes with offline stub, browser tests, container isolation, and telemetry. Stage C runs repeated configured real-model evaluations, baseline comparisons, and extension proofs. At every boundary: builder evidence → independent tester → explicit human acceptance. If one agent executes all roles sequentially, label independence unavailable. Report skipped model/runtime/clinician checks as skipped.

## Review revision (2026-09-25)

Contract v0.3 resolves inventory-based lab/vital selection, atomic exact-ID reads, persisted review state, and active/interrupted run replay. The evaluator now rejects malformed traces, absent injected tool faults, mismatched retries, and empty evaluation files. Schemas and component handoffs match these rules. Patient fixtures and expected clinical answers are unchanged. This is a kit review; runtime implementation and acceptance remain pending.

## Runnable kit checks

From the repository root, run exactly:

```bash
python3 evaluation/scripts/validate_kit.py
python3 -m unittest discover -s evaluation -p 'test_*.py'
```

These check the supplied kit and structured fixtures. They do not start the application or establish semantic/clinical correctness. Missing evaluation checker or fixture files are an incomplete package, not a passing check.

## Data and evaluation boundaries

Synthetic runtime records live in `records-mcp/data/patients/*.json`. Evaluator-only answers live in `evaluation/cases/dev.jsonl` (12 development cases) and `evaluation/cases/candidate_holdout.jsonl` (eight patient-disjoint candidate cases). Fix `as_of` for evaluation. Fault plans, expected calls/outputs, scenario labels, and scores belong only to the evaluator; never place them in patient records, model context, browser assets, runtime imports, or runtime mounts. Grade required read coverage/dependencies rather than one exact call order or batch shape.

**Candidate holdout is visible in this package and is not blind.** Freeze it before tuning and reserve execution for the independent evaluator. Fresh clinician-reviewed cases are needed for stronger release claims. Stub results prove plumbing; real-model repetitions and human semantic/source review remain separate requirements. The static grader cannot validate unsupported free-text clinical claims.

## Keep extensions small

Retain the fixed stack and small ModelPort/MCP/persistence/telemetry interfaces. Add a tool through typed handler, schema, explicit registration, approved client allowlist, and contract/evaluation fixtures. Add a server through the same adapter and a reviewed `agent-service/config/mcp_servers.json` entry with server-specific credentials; never accept arbitrary URLs or automatically enable discovered tools. Prove optional same-server `get_record_counts` and second-server `ping` without coordinator/UI edits; neither enters the clinical allowlist by default. The orchestrator assigns shared config, contract, script, and development-fixture work within the authorized implementation scope without extra confirmation. Preserve frozen holdout/goldens and present intentional scope changes for human decision.
