---
name: verify-clinician-mvp
description: Independently test clinician kit and runtime stages, enforce evidence and evaluator isolation, and prepare explicit human acceptance without overstating clinical validity.
---

# Verify the stage

## Inputs and ownership

Read `../build-clinician-mvp/references/contracts.md` and `../build-clinician-mvp/references/sources.md`, root `AGENTS.md`, component handoffs, the assigned stage, and raw builder artifacts. Read evaluator instructions before accessing `evaluation/cases/dev.jsonl` and `evaluation/cases/candidate_holdout.jsonl`.

Own the test verdict, evaluator reports, and harness/test paths assigned by the orchestrator within the authorized implementation scope. Coordinate shared script, config, contract, and development-fixture work through that owner; send application defects to builders to preserve independent review. Keep holdout/goldens frozen against tuning and never rewrite expected answers to make failures pass. Escalate genuine benchmark defects as explicit versioned corrections with affected results invalidated.

## Steps

1. Verify Stage A using `python3 scripts/validate_kit.py` and `python3 -m unittest discover -s . -p 'test_*.py'` from `evaluation/`. Confirm exact schema/fixture consistency and dependency compatibility evidence separately. A successful static kit check does not prove an implemented application.
2. Verify Stage B against three actual processes and the isolated MCP container with the offline stub. Exercise HTTP routes and browser journeys; inspect authorization, interleaved patient/trace isolation, schema and result limits, provenance, date/numeric fidelity, uncertainty, empty versus outage behavior, escaped injection, timeouts/retry budgets, cancellation, 429, idempotency, database failure/restart, feedback versions, and saved-output access during outage.
3. Inspect runtime mounts and imports/context to ensure only MCP reads patient records and no model, tool, browser, or runtime service receives golden answers, scenario metadata, fault plans, or evaluator scores. Inject faults through test-only harness setup; never public tool arguments.
4. Grade 12 development and eight patient-disjoint candidate holdout cases at fixed `as_of`. Check required/optional reads, dependencies and forbidden tools rather than exact order/batching. Require every clinical fact to cite successfully read evidence; check expected structured output and prohibited assertions. Preserve contradictory evidence and explicit uncertainty.
5. Verify Stage C with repeated configured real-model runs and fixed-baseline versus adaptive comparisons. Record latency, usage (unknown if absent), errors, retries, and budget outcomes. Prove an optional same-server `get_record_counts` and a second test-only server's `ping` without coordinator/UI changes; neither belongs to the default clinical allowlist.
6. Check correlated spans/logs, redaction, queue bounds, collector outage behavior, log rotation/retention, and persistence independence. Keep audit events in SQLite distinct from operational telemetry.
7. Freeze candidate holdout before tuning and reserve it for the independent evaluator. State that it is visible, not blind, and insufficient for clinical benchmark claims. Require fresh clinician-reviewed cases for stronger claims. Treat the static grader as a starting point; arrange human review of semantic citation support, omissions, and unsupported free text.

## Outputs and tests

Return changed paths (if any), exact commands, observed pass/fail/skip counts, raw run references, case/control coverage, reproducible failures, and acceptance blockers. Separate kit, stub, real-model, browser, container, extension, and clinician results. Do not infer an independent review when one agent performed every role.

## Tester → human gate

Return failures to the owning builder and rerun affected checks. At each Stage A/B/C boundary, submit the completed review and limitations to the human through the orchestrator. Require explicit human acceptance before the next stage; never mark skipped tests or pending clinician review passed.
