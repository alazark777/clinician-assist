# Project-local coding instructions

Read the installed `~/.cursor/skills/build-clinician-mvp/SKILL.md` and repository source references at `../skills/build-clinician-mvp/references/contracts.md` and `sources.md` before work. The references are authoritative; the current MCP-in-MVP architecture supersedes the retained v0.1 deferral. Root `skills/` is source material, not a runtime package. Read the selected installed skill and component README/developer guide. Prefer the fixed stack, stable schemas, and small adapters over parallel frameworks or bespoke orchestration.

## Scope and ownership

This repository starts as an implementation kit. Use these instructions to build the application within the user's authorized implementation scope. Let the orchestrator assign the stage, file ownership, and interfaces, including shared-file work, without additional confirmation for routine implementation decisions.

| Role | Implementation ownership |
|---|---|
| Orchestrator | evaluation README, skills, integration files, and assignment of shared-file ownership |
| Web builder | `web/**`, including browser tests |
| Agent builder | `agent-service/**`, migrations and runtime `var/agent/` |
| Records builder | `records-mcp/**`, including container definitions |
| Telemetry builder | component-local telemetry instructions; coordinate component call sites with their owners |
| Independent tester | Verdict, evaluator reports, and assigned harness/test paths |

Let the orchestrator assign shared config, contracts/references, scripts, development fixtures, and evaluator harness changes to one owner within the authorized implementation scope. No extra user confirmation is needed for those assignments. Keep holdout/goldens frozen against tuning; surface genuine benchmark defects as versioned corrections rather than changing answers to pass. Present intentional scope changes for explicit human decision. Do not overwrite concurrent work. Coordinate cross-boundary edits with their owners. Give each delegate inputs, stage, owned paths, deliverables, required tests, and gate. If delegation is unavailable, execute sequentially and disclose that independent review is unavailable.

## Implementation invariants

- Build web → agent HTTP API/MCP client → separate records MCP; only records MCP reads patient files. Use one clinical runtime coordinator.
- Keep goldens/fault plans/scenario labels out of runtime records, context, imports, assets, and mounts. Reserve candidate holdout for evaluation; it is visible and not blind.
- Use per-request verified patient scope, explicit discovered-tool allowlists, pinned official SDK handling, and strict schemas. Never pass browser/provider credentials to MCP or derive scope from model text/baggage.
- Preserve fixed retrieval/model budgets, source/date/numeric validation, uncertainty, conflicts, and empty-versus-outage semantics. Persist authoritative runs and versioned feedback; never write source records.
- Keep patient/clinical data and secrets out of operational telemetry. Prove isolation, concurrent request separation, and persistence despite telemetry failure.
- Extend tools/servers through typed registration and registry adapters, preserving coordinator/UI code. Do not silently change the contracted stack/protocol or default clinical allowlist.

## Evidence and tester → human gates

Run from `evaluation/`:

```bash
python3 scripts/validate_kit.py
python3 -m unittest discover -s . -p 'test_*.py'
```

These commands validate kit structure and fixtures only. Component startup and
runtime checks live in the component directories; record their observed
evidence separately from static evaluator results. Pin exact dependencies
after official-source compatibility checks and record observed evidence.

At each Stage A/B/C boundary, collect changed paths, command results, pass/fail/skip counts, limitations, and unresolved risks. Require independent tester review, defect resolution, then explicit human acceptance before advancing. Distinguish static, stub, real-model, browser, container, extension, and clinician evidence. Never claim skipped checks passed or prototype acceptance establishes clinical validation.
