---
name: build-clinician-mvp
description: Orchestrate delegated coding agents to implement the clinician MVP from this project-local kit, with fixed contracts, independent testing, and human stage acceptance.
---

# Orchestrate the build

## Inputs and ownership

Read `references/contracts.md` and `references/sources.md` as the authoritative current contract. Treat `references/source-mvp-v0.1.md` as historical where it conflicts. Read root `AGENTS.md`, component handoffs, registry, and available fixture/checker instructions.

Own `evaluation/README.md`, `evaluation/AGENTS.md`, and evaluation integration files. Delegate `web/**`, `agent-service/**`, `records-mcp/**`, and component-local observability paths to their respective owners. Assign shared config, contracts/references, scripts, development fixtures, and evaluator harness work to a single owner within the authorized implementation scope; routine assignments need no additional user confirmation. Reserve evaluator reports and frozen answers for the tester. Never overwrite another agent's work or alter holdout/goldens to accommodate tuning. Surface intentional scope changes for explicit human decision.

## Steps

1. Inventory existing files before scaffolding. Establish the implementation stage, assign owners and interfaces, and proceed within the authorized scope. Coordinate shared-file changes as part of the build; preserve frozen evaluation answers and handle intentional scope changes explicitly.
2. Preserve React/TypeScript/Vite → FastAPI agent API/MCP client → isolated Python MCP records server. Build one runtime coordinator. Use ModelPort, record adapter, persistence, and telemetry interfaces; avoid optional frameworks and alternate stacks.
3. Execute Stage A: freeze interfaces and command/env conventions, run the two root kit checks, and verify exact dependencies against official releases in `sources.md`. Resolve Python/npm lockfiles and image digests once. Record actual SDK 2.x/protocol 2026-07-28 compatibility or a concrete blocker in README; never claim compatibility from this kit alone.
4. Delegate Stage B using `../build-clinician-web/SKILL.md`, `../build-clinician-agent/SKILL.md`, `../build-clinician-records/SKILL.md`, and `../instrument-clinician-mvp/SKILL.md`. Give each agent authoritative paths, stage, input interfaces, exact writable paths, required commands/tests, and handoff format. Parallelize disjoint work; serialize integration edits. Deliver three real processes, offline stub, MCP isolation, telemetry, and browser journeys.
5. Delegate Stage C evaluation to `../verify-clinician-mvp/SKILL.md`. Run configured real-model repetitions, fixed-baseline comparison, and tool/server extension proofs. Keep evaluator answers and fault plans out of runtime context. Do not tune on candidate holdout.
6. Require each builder to return changed paths, interface changes, command results, limitations, and unresolved risks. Route defects to the owning builder and retest. If delegation is unavailable, execute roles sequentially and mark independent review unavailable.

## Outputs and tests

Deliver the stage's code/docs, reproducible commands, locked compatibility evidence, and a consolidated test report with passed/failed/skipped status. Run from `evaluation/`: `python3 scripts/validate_kit.py` and `python3 -m unittest discover -s . -p 'test_*.py'`. Require actual component startup, contract, browser, isolation, concurrency, persistence, and extension evidence for implementation stages; static checks are insufficient.

## Tester → human gate

At **each** Stage A/B/C boundary, send concrete deliverables and test evidence to the independent tester, resolve failures, then request explicit human acceptance before starting the next stage. Include pending real-model or clinician review and independence limitations. Never relabel skipped work as passed or infer clinical validation from prototype acceptance.
