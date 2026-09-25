---
name: build-clinician-web
description: Implement the delegated React clinician web component against the fixed agent HTTP contract, with source-linked drafts, feedback, and browser verification.
---

# Build the web component

## Inputs and ownership

Read `../build-clinician-mvp/references/contracts.md` and `../build-clinician-mvp/references/sources.md`, root `AGENTS.md`, `web/README.md`, and `web/DEVELOPER_GUIDE.md`. Take the orchestrator's stage, HTTP schemas, and explicit assignment as inputs.

Own `web/**`, including component tests and handoff docs, plus shared paths assigned by the orchestrator within the authorized implementation scope. Coordinate interface changes and ownership before cross-component edits; do not overwrite another owner's work. Preserve frozen holdout/goldens against tuning.

## Steps

1. Implement React + TypeScript + Vite on localhost:5173 using the canonical component commands. Fetch only the agent API through `VITE_AGENT_API_BASE_URL`; never read patient files, connect to MCP/model providers, or embed server secrets.
2. Use the opaque demo session and authorized patient catalog. Implement patient selection, visit context, fixed `as_of`, generation, saved-profile reload, and version-bound accept/needs-correction feedback. Preserve the request ID for a retry of identical input; issue a new ID when input changes or the user explicitly restarts an interrupted run. Poll the contracted run route after 202; never silently restart work.
3. Render condition, medication, allergy, lab, and vital facts with source excerpts and versions. Show gaps, conflicts, draft/review status, incomplete retrieval, and returned run ID. Distinguish missing evidence, empty inventory, and outage; never infer a negative finding.
4. Escape record text and model output; avoid unsafe HTML, remote scripts, or interpreting notes as instructions. Abort requests on cancellation and prevent late responses from replacing another patient's view.
5. Persist and display the returned review status/revision, and bind feedback to both version fields. Handle 403/422/409/429/502/503 and network errors using safe messages. Keep clinical values, patient identifiers, payloads, and credentials out of frontend logs. Accept records demo feedback only; expose no prescribing, orders, diagnoses, or record-write action.
6. Keep rendering driven by the stable profile schema. Add new approved tools/servers in backend adapters and the registry; require no UI changes for the optional count/ping extension proofs.

## Outputs and tests

Deliver the component, lockfile, updated handoffs, changed paths, and evidence for `npm --prefix web run dev -- --host 127.0.0.1 --port 5173`, `npm --prefix web run build`, and `npm --prefix web run test:e2e`. Implement those commands before claiming success. Use Playwright against the real HTTP pipeline for selection → generation → sources → feedback → reload, empty/incomplete/error states, escaped injection, authorization, duplicate submissions, and cancellation/patient-switch races. Keep goldens outside browser bundles and fixtures served to the application.

## Tester → human gate

Submit browser results and reproducible journeys to `verify-clinician-mvp`; fix reported defects. Return to the orchestrator for explicit human stage acceptance after tester review. Mark mocked-only, skipped runtime, and pending clinician checks accurately; do not advance stages independently.
