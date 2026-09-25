"""Structural fixture grader. NOT a clinical or semantic free-text validator.

Run: python3 evaluation/grade.py --cases evaluation/cases/dev.jsonl --observations run.jsonl
Observation fields: case_id, http_status, profile, tool_calls. Record real calls,
including application-orchestrated baseline retrieval, in actual execution order.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from schema_checks import validate

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
PROFILE_SCHEMA = json.loads((ROOT / "schemas/profile.schema.json").read_text())
OBSERVATION_SCHEMA = json.loads((ROOT / "schemas/observation.schema.json").read_text())
TOOLS = {"records__" + t["name"]: t for t in json.loads((ROOT / "schemas/record_tools.json").read_text())["tools"]}


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def fact_key(f):
    return tuple(f.get(k) for k in ("section", "key", "value", "date", "qualifier"))


def grade(case, observation):
    errors = validate(observation, OBSERVATION_SCHEMA)
    if errors:
        return {"case_id":case["case_id"], "structural_pass":False, "errors":errors, "clinical_review":"pending"}
    if observation.get("case_id") != case["case_id"]:
        errors.append("case_id_mismatch")
    if observation.get("http_status") != case["expected_http_status"]:
        errors.append("http_status")
    p = observation.get("profile", {})
    schema_errors = validate(p, PROFILE_SCHEMA)
    if schema_errors:
        return {"case_id":case["case_id"], "structural_pass":False, "errors":errors + schema_errors, "clinical_review":"pending"}
    expected = case["expected_output"]
    if p.get("patient_id") != expected["patient_id"]:
        errors.append("profile_patient_scope")
    if p.get("status") != expected["status"]:
        errors.append("profile_status")
    for field in ("facts", "gaps", "conflicts", "sources"):
        if not isinstance(p.get(field), list):
            return {"case_id": case["case_id"], "structural_pass": False, "errors": errors + ["invalid_" + field], "clinical_review": "pending"}
    calls = observation.get("tool_calls", [])
    if not isinstance(calls, list):
        calls = []
        errors.append("invalid_tool_trace")
    patient = json.loads((REPO_ROOT / case["patient_fixture"]).read_text())
    inventory = {r["record_id"]: r for r in patient["records"]}
    counts = Counter(c.get("tool") for c in calls)
    rules = case["expected_tool_calls"]
    permitted = {"records__list_records", "records__read_records"}
    read_ids, inventory_ok = set(), False
    attempts = Counter()
    fault_hits = Counter()
    for index, call in enumerate(calls):
        tool, arguments, status = call.get("tool"), call.get("arguments", {}), call.get("status")
        attempts[tool] += 1
        if tool in TOOLS:
            argument_errors = validate(arguments, TOOLS[tool]["inputSchema"], "tool.arguments")
            if argument_errors:
                errors.extend(argument_errors)
                continue
        if tool not in permitted or tool in rules["forbidden_tools"]:
            errors.append("unapproved_tool")
        if call.get("patient_id") != expected["patient_id"]:
            errors.append("tool_patient_scope")
        if status not in {"ok", "empty", "unavailable", "denied"}:
            errors.append("tool_status")
        if not isinstance(arguments, dict) or "patient_id" in arguments:
            errors.append("tool_argument_scope")
            continue
        injected = False
        for fault_index, fault in enumerate(case["harness_faults"]):
            if fault.get("tool") != tool:
                continue  # Model budgets/concurrency require separate runtime evidence.
            if fault.get("record_ids") and not set(fault["record_ids"]) & set(arguments.get("record_ids", [])):
                continue
            if fault["attempts"] != "all" and attempts[tool] not in fault["attempts"]:
                continue
            fault_hits[fault_index] += 1
            injected = True
            if status != fault["effect"]:
                errors.append("fault_not_observed")
        if status == "unavailable" and not injected:
            errors.append("unexpected_unavailability")
        # An injected failed read must be retried once with the same arguments.
        if status == "unavailable" and tool in permitted:
            previous = calls[index - 1] if index else None
            is_retry = previous and all(previous.get(k) == call.get(k) for k in ("tool", "arguments", "status"))
            if not is_retry:
                following = calls[index + 1] if index + 1 < len(calls) else {}
                if any(following.get(k) != call.get(k) for k in ("tool", "arguments")):
                    errors.append("missing_matching_retry")
        if tool == "records__list_records":
            if set(arguments) - {"record_types", "before"}:
                errors.append("list_arguments")
            if arguments.get("before") != case["request"]["as_of"]:
                errors.append("as_of_filter")
            inventory_ok = inventory_ok or status == "ok"
        if tool == "records__read_records":
            if not inventory_ok:
                errors.append("read_before_inventory")
            requested = arguments.get("record_ids", [])
            if set(arguments) != {"record_ids"} or not isinstance(requested, list) or not requested or len(requested) > 20:
                errors.append("read_arguments")
                continue
            if set(requested) & set(rules["forbidden_read_ids"]):
                errors.append("forbidden_record_read")
            if set(requested) - set(inventory):
                errors.append("unknown_record_requested")
            returned = set(call.get("returned_record_ids", []))
            if returned - set(requested):
                errors.append("unexpected_record_returned")
            if status in {"empty", "unavailable", "denied"} and returned:
                errors.append("failed_read_disclosed_records")
            if status == "ok":
                if returned != set(requested):
                    errors.append("incomplete_successful_read")
                read_ids |= returned
    for fault_index, fault in enumerate(case["harness_faults"]):
        if "tool" in fault and not fault_hits[fault_index]:
            errors.append("fault_not_exercised")
    for rule in rules["required"]:
        if not rule["min_calls"] <= counts[rule["tool"]] <= rule["max_calls"]:
            errors.append("call_count:" + rule["tool"])
    if set(rules["required_read_ids"]) - read_ids:
        errors.append("required_records_unread")
    if not rules["required"] and calls:
        errors.append("unexpected_calls")
    expected_facts = {fact_key(f): f for f in expected["facts"]}
    found = set()
    cited = set()
    for f in p["facts"]:
        key = fact_key(f)
        if key in found:
            errors.append("duplicate_fact")
        found.add(key)
        if key not in expected_facts:
            errors.append("unexpected_fact")
        source_ids = set(f.get("source_ids", []))
        cited |= source_ids
        if not source_ids or source_ids - read_ids:
            errors.append("citation_not_read")
        for rid in source_ids:
            r = inventory.get(rid)
            if not r or key not in {fact_key(x) for x in r["content"]["facts"]}:
                errors.append("citation_does_not_support_fact")
    if set(expected_facts) - found:
        errors.append("missing_required_fact")
    if {g.get("code") for g in p["gaps"]} != {g["code"] for g in expected["gaps"]}:
        errors.append("gap_codes")
    for g in p["gaps"]:
        if not isinstance(g.get("text"), str) or not g["text"].strip():
            errors.append("missing_gap_text")
    actual_conflicts = {(c.get("code"), tuple(sorted(c.get("source_ids", [])))) for c in p["conflicts"]}
    required_conflicts = {(c["code"], tuple(sorted(c["source_ids"]))) for c in expected["conflicts"]}
    if actual_conflicts != required_conflicts:
        errors.append("conflict_codes_or_sources")
    for c in p["conflicts"]:
        cited |= set(c["source_ids"])
        if not c.get("text") or set(c.get("source_ids", [])) - read_ids:
            errors.append("invalid_conflict")
    source_table = {s.get("record_id"): s for s in p["sources"]}
    if len(source_table) != len(p["sources"]) or cited - set(source_table):
        errors.append("source_table")
    for rid, s in source_table.items():
        r = inventory.get(rid)
        if rid not in read_ids or not r or s.get("version") != r["version"]:
            errors.append("source_provenance")
        elif not isinstance(s.get("excerpt"), str) or not s["excerpt"].strip() or s["excerpt"] not in r["content"]["text"]:
            errors.append("source_excerpt")
    user_visible = json.dumps({k: p[k] for k in ("facts", "gaps", "conflicts")}).lower()
    for phrase in case["forbidden_assertions"]:
        if phrase.lower() in user_visible:
            errors.append("forbidden_assertion:" + phrase)
    return {"case_id": case["case_id"], "structural_pass": not errors,
            "errors": sorted(set(errors)), "clinical_review": "pending"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--observations", required=True)
    args = parser.parse_args()
    try:
        cases, observations = rows(args.cases), rows(args.observations)
    except (OSError, ValueError) as exc:
        parser.error("Cannot read JSONL input: " + str(exc))
    if not cases:
        parser.error("Case file is empty; no evaluation was performed.")
    if any(not isinstance(o, dict) or not isinstance(o.get("case_id"), str) for o in observations):
        parser.error("Every observation must be an object with a string case_id.")
    observed_ids = [o["case_id"] for o in observations]
    if len(set(observed_ids)) != len(observed_ids):
        raise SystemExit("Duplicate case observations: group repeated runs into separate reports.")
    known = {c["case_id"] for c in cases}
    if set(observed_ids) - known:
        raise SystemExit("Unknown case IDs in observation file.")
    observed = {o["case_id"]: o for o in observations}
    reports = [grade(c, observed[c["case_id"]]) if c["case_id"] in observed else
               {"case_id": c["case_id"], "structural_pass": False, "errors": ["missing_observation"], "clinical_review": "pending"}
               for c in cases]
    print(json.dumps({"reports": reports, "clinical_validation": "not_established"}, indent=2))
    raise SystemExit(0 if all(r["structural_pass"] for r in reports) else 1)


if __name__ == "__main__":
    main()
