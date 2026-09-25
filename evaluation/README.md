# Synthetic evaluation suite

Contains 20 authored scenarios and 21 patient fixtures (one extra patient is used for a concurrency challenge). All names, values and situations are fictional. Twelve cases are for development; eight are **candidate holdout**, visible in this kit and not a blind or clinically validated benchmark.

## What to evaluate

Each JSONL row supplies a request/caller, fixture path, harness-only fault plan, expected HTTP status, expected structured profile, expected tool coverage, representative trace, prohibited assertions and human review checks. The scenario ID, golden output and fault plan must never enter a model prompt or MCP mount. The real model receives only the clinical request and authorized MCP results.

`expected_tool_calls.representative_sequence` is illustrative. `required` and `required_read_ids` define necessary coverage. Read batching and fact order can vary. The trace includes both deterministic baseline tool calls and model-selected calls, with verified effective patient scope. Include failed attempts. Test the request-scoped context collision in E18 with an actual second concurrent request; a P018-only golden comparison cannot prove isolation.

Harness faults must be injected out of band into test doubles, transports or test-only server boot configuration. Never enable a production-facing fault endpoint or expose faults as model tool parameters. For E17, inject failure only when the earlier record is read. For E19, exhaust the model budget after baseline retrieval and assert no more work is scheduled.

## Commands available in this kit

From the `evaluation/` directory:

```bash
python3 scripts/validate_kit.py
python3 -m unittest discover -s . -p 'test_*.py'
python3 grade.py --cases cases/dev.jsonl --observations var/observations.jsonl
```

The last command requires observations from an implemented service. The first two validate fixtures and the grader only. `scripts/build_fixtures.py` reproducibly rebuilds fixtures; do not regenerate a frozen evaluation set to accommodate a failing model.

## Observation format and limits

Validate against `schemas/observation.schema.json` before grading. One JSON object per line: `case_id`, `http_status`, `profile`, `tool_calls`. The profile follows the shared contract. Each call has qualified `tool`, `arguments`, effective `patient_id`, `status`, and `returned_record_ids` (successfully returned full records only; inventory metadata does not count as a read). Build these from actual execution events, never from expected traces. Runtime IDs and cost/latency may be attached separately. For pre-profile errors, the harness normalizes the HTTP error into the failed profile shape used by the case; it must preserve the real HTTP code.

The supplied grader checks exact factual tuple values/dates/qualifiers, citation support against structured source facts, source excerpts, gap/conflict codes, scope, tool coverage and order dependencies. It rejects malformed observations, missing fault effects, mismatched retries and reads after an empty inventory. It checks exact-ID successful batch coverage. These checks cannot prove that a harness actually executed a fault; retain runtime evidence separately. It accepts reordered facts/reads, but is deliberately conservative about alternate factual encodings. It is **not** a medical semantic grader. Meaning of gap prose, clinically important omissions beyond the authored cases, and newly invented medical recommendations need clinician review. A passing report always says clinical review pending.

Implement separate reports for deterministic stub pipeline checks, fixed-baseline real-model runs, adaptive-agent real-model runs (three trials/case), browser tests and human review. Missing model credentials or reviewer access means skipped/pending, never passed. Safety/control failures block acceptance regardless of aggregate scores. Log only redacted execution data; store detailed synthetic eval observations separately under ignored `var/evaluation/`.
