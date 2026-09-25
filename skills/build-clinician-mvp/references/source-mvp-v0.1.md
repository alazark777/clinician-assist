# Clinician Assistant — MVP Agent Design v0.1

**Status:** Draft for review. This document defines the first build; implementation and clinical validation have not begun.

## 1. Use case and scope

Help a clinician prepare for an outpatient diabetes follow-up by producing a concise, source-linked patient profile. Include documented conditions, medications, allergies, relevant recent results, and information gaps. Keep additional documented conditions visible when relevant to the visit.

**Working assumptions:** Use synthetic patients, English text records, one selected patient per request, and read-only access to source records. Treat the output as a draft for clinician review. Diagnosis, treatment recommendations, clinical risk scoring, orders, and chart updates are outside this MVP.

Run a minimal web application and the agent service as separate local processes connected through HTTP. Containers, MCP, A2A, and reusable cross-patient memory are later extensions. This is the new implementation baseline; the earlier payment-dispute design does not govern this build.

## 2. Concrete input and expected output

**Clinician request:** Patient `P001` — “Prepare a brief patient profile before today's diabetes follow-up.”

**Available synthetic records:**

| Source | Record date | Content |
|---|---|---|
| R1 — Visit note | 2026-06-10 | Type 2 diabetes. Medication list: metformin 500 mg twice daily. |
| R2 — Lab result | 2026-09-15 | HbA1c: 7.8%. |
| R3 — Allergy record | 2026-03-03 | Penicillin — rash. |

**Expected profile:**

> **Patient P001 — Pre-visit profile**
>
> - **Documented condition:** Type 2 diabetes. [R1]
> - **Last documented medication:** Metformin 500 mg twice daily, recorded June 10, 2026. Current use has not been confirmed. [R1]
> - **Recorded allergy:** Penicillin — rash. [R3]
> - **Latest available HbA1c:** 7.8% on September 15, 2026. [R2]
> - **Information gaps:** No earlier HbA1c result is available for comparison. No current vital signs were supplied.

Use this as evaluation case E01. Equivalent wording is acceptable; facts, dates, uncertainty, and source support must be preserved. “Not available” means absent from the accessible record set, not absent from the patient's medical history.

## 3. Data and tools

Store versioned synthetic JSON records under `records-mcp/data/patients/`. Each record carries `patient_id`, `record_id`, `record_type`, `recorded_at`, clinical event date when known, content, and source version. Include explicit medication status when supplied; never infer current use solely from recency. Package a complete, bounded record inventory for each fixture patient.

Expose two read tools behind a replaceable record-store interface:

| Tool | Inputs | Output |
|---|---|---|
| `list_records` | Allowed record types; optional date range | Patient-scoped record IDs, types, dates, and inventory coverage. |
| `read_records` | Record IDs from that inventory | Original record content, dates, and provenance. |

The application binds the authorized patient scope; the model cannot select another patient. Distinguish `ok`, `empty`, `unavailable`, and `denied`. Report incomplete or failed retrieval explicitly. Only a completed inventory check can support a claim that no matching record is available. Local functions are sufficient initially; later HTTP/MCP adapters must preserve these contracts.

## 4. Workflow and service boundary

1. **Validate:** Check patient selection, caller access, request schema, and configured limits.
2. **Gather baseline:** Application code inventories the selected patient's records and loads documented conditions, medication/allergy records, latest relevant results, and the latest visit note.
3. **Investigate selectively:** The model may request additional records to resolve a discrepancy or look for an earlier comparable result. For example, it can inspect older medication notes when two lists disagree. Preserve unresolved conflicts instead of choosing an unsupported answer.
4. **Draft and check:** Produce typed profile sections with claim-level source IDs and dates. Code checks schema, patient scope, source existence, and mandatory sections. A source ID alone does not prove that its text supports the claim; evaluation checks that separately.
5. **Return for review:** Display the draft with clickable source excerpts, retrieval limitations, and missing information. The clinician can accept it for the demo or flag a correction; neither action writes to the clinical source records.

Use a bounded model/tool loop only for step 3 and drafting. Compare it with a fixed retrieval-and-summary baseline during evaluation to establish whether adaptive retrieval improves the result.

**Proposed local defaults:** Python/FastAPI agent service, a separate minimal web UI, JSON source fixtures, and SQLite for run history and reviewer feedback. Keep model, tools, storage, and telemetry behind small interfaces. These are draft choices, not requirements inherited from the previous project.

| Endpoint | Purpose |
|---|---|
| `GET /v1/patients` | List authorized synthetic patient choices. |
| `POST /v1/profiles` | Accept patient ID and visit context; return profile ID, status, structured profile, sources, and limitations. |
| `GET /v1/profiles/{id}` | Retrieve an authorized saved profile. |
| `POST /v1/profiles/{id}/feedback` | Record accept/needs-correction feedback bound to that profile version. |

Use synchronous generation initially. Bound runs to six model calls, ten additional record reads, and 60 seconds; permit at most one transient read retry within those limits. These are initial engineering limits to measure and revise. On exhaustion, return an explicit incomplete result using verified material, or a structured failure; never imply complete chart coverage.

Persist request, source snapshot/version references, output, status, feedback, and run ID. Emit correlated model/tool events, latency, and token usage without private model reasoning or raw records in routine logs. Bind local endpoints to loopback. Record content is untrusted data and cannot grant tool permissions. Provide a deterministic model stub for offline tests and one configurable real-model adapter for agent evaluation. Stub success does not establish model quality.

## 5. Evaluation before implementation

After reviewing this draft, create a proposed starter set of **20 synthetic patient scenarios**: 12 for development and eight held out for final acceptance. Split by patient and avoid near-duplicate scenario variants across the split. Freeze the holdout before prompt/tool tuning; expand it as failures are discovered.

Each case contains the request, source records, required facts, supporting source IDs, expected gaps/conflicts, forbidden claims, and allowed tool access. Grade supported outcomes rather than one exact wording or tool-call sequence. Include routine profiles, missing allergies, outdated medication lists, conflicting notes, multiple result dates, empty records, retrieval failure, embedded instructions, and wrong-patient access attempts.

**Proposed MVP gates:** Every mandatory control test passes; held-out outputs contain the required facts and no unsupported clinical assertions or incorrect patient references. Check schemas, dates, permissions, and citation existence automatically. Have a clinician review factual support, important omissions, and usefulness; an LLM grader may assist. Record latency, token usage, and retrieval steps for both the baseline and agent. This small dataset supports prototype acceptance, not clinical deployment validation.

## 6. Build and acceptance sequence

1. Review this single document, especially scope and output format.
2. Create fixtures and the scoring rubric, then implement the simplest retrieval-and-summary baseline.
3. Build the separate web app, agent endpoint, bounded adaptive retrieval, tracing, and feedback flow.
4. Run an independent tester against the actual HTTP pipeline, then hand the runnable MVP to a human for acceptance. Label any unperformed clinician review as pending. Advance to later extensions only after explicit human acceptance.

Keep updates in this document and executable tests. Additional design documents are unnecessary for this MVP.

**Design references:** [Anthropic: success criteria and evaluations](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests); [Anthropic: agent evaluations](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents); [WHO: well-defined health AI tasks and stakeholder involvement](https://www.who.int/news/item/18-01-2024-who-releases-ai-ethics-and-governance-guidance-for-large-multi-modal-models).
