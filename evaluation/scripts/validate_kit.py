"""Validate this authored kit without third-party packages or model/network calls."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evaluation"))
from grade import rows, grade
from schema_checks import validate


def main():
    errors = []
    def check(ok, message):
        if not ok:
            errors.append(message)
    cases = rows(ROOT / "evaluation/cases/dev.jsonl") + rows(ROOT / "evaluation/cases/candidate_holdout.jsonl")
    check(len(cases) == 20, "need 20 cases")
    check(len({c["case_id"] for c in cases}) == 20, "case IDs must be unique")
    check(sum(c["split"] == "dev" for c in cases) == 12, "need 12 dev cases")
    dev = {c["request"]["patient_id"] for c in cases if c["split"] == "dev"}
    holdout = {c["request"]["patient_id"] for c in cases if c["split"] == "candidate_holdout"}
    check(not dev & holdout, "patient leakage across splits")
    for c in cases:
        p = ROOT / c["patient_fixture"]
        check(p.is_file(), "missing patient fixture " + str(p))
        if not p.is_file():
            continue
        patient = json.loads(p.read_text())
        check(patient["patient_id"] == c["request"]["patient_id"], c["case_id"] + ": scope mismatch")
        check(len({r["record_id"] for r in patient["records"]}) == len(patient["records"]), c["case_id"] + ": duplicate IDs within patient")
        check(c["clinical_review_status"] == "not_reviewed", "unsupported clinical review claim")
        observation = {"case_id": c["case_id"], "http_status": c["expected_http_status"], "profile": c["expected_output"], "tool_calls": c["expected_tool_calls"]["representative_sequence"]}
        verdict = grade(c, observation)
        check(verdict["structural_pass"], c["case_id"] + ": inconsistent golden " + str(verdict["errors"]))
        if c.get("companion_fixture"):
            check((ROOT / c["companion_fixture"]).is_file(), "missing concurrent patient")
    for p in (ROOT / "records-mcp/data/patients").glob("*.json"):
        raw = p.read_text()
        schema = json.loads((ROOT / "evaluation/schemas/patient.schema.json").read_text())
        check(not validate(json.loads(raw), schema), "patient schema violation " + p.name)
        for key in ("expected_output", "expected_tool_calls", "harness_faults", "case_id", "split"):
            check('"' + key + '"' not in raw, f"golden leakage into {p.name}: {key}")
    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    check(len(skills) == 6, "need six coding skills")
    for p in skills:
        raw = p.read_text()
        front = re.match(r"---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n---", raw)
        check(bool(front), "invalid skill frontmatter: " + str(p))
        if front:
            check(front.group(1) == p.parent.name, "skill directory/name mismatch")
        check("contracts.md" in raw and "sources.md" in raw, "missing shared contract references")
    for component in ("web", "agent-service", "records-mcp"):
        for name in ("README.md", "DEVELOPER_GUIDE.md"):
            check((ROOT / component / name).is_file(), f"missing {component}/{name}")
    ignored_doc_parts = {
        ".venv",
        "node_modules",
        "playwright-report",
        "test-results",
        "var",
    }
    for p in ROOT.rglob("*.md"):
        if ignored_doc_parts.intersection(p.relative_to(ROOT).parts):
            continue
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", p.read_text()):
            if re.match(r"https?://|mailto:|#", target):
                continue
            check((p.parent / target.split("#")[0]).exists(), f"broken link {p.relative_to(ROOT)} → {target}")
    registry = json.loads((ROOT / "agent-service/config/mcp_servers.json").read_text())
    check(len({s["id"] for s in registry["servers"]}) == len(registry["servers"]), "duplicate server IDs")
    for server in registry["servers"]:
        check(server["url"].startswith("http://127.0.0.1:"), "local registry should use loopback")
        check(
            (ROOT / "agent-service/config" / server["approved_schema_file"]).is_file(),
            "missing approved schema",
        )
    print(json.dumps({"status": "FAIL" if errors else "PASS", "cases":len(cases), "patients":len(list((ROOT / "records-mcp/data/patients").glob("*.json"))), "skills":len(skills), "errors":errors,
          "scope":"Kit structure and golden consistency only; runtime, MCP conformance, model quality and clinical review not tested."}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
