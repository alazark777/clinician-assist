#!/usr/bin/env python3
"""Stage C evaluator entrypoint: runtime cases, extensions, regressions, report."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "evaluation"
HARNESS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))

from grade import grade, rows  # noqa: E402
from harness.baseline_compare import compare_baseline_adaptive  # noqa: E402
from harness.case_runner import load_cases, run_case  # noqa: E402
from harness.extensions import (  # noqa: E402
    prove_get_record_counts,
    prove_ping_server,
    prove_registry_load_without_coordinator_change,
)
from harness.model_config import (  # noqa: E402
    real_model_configured,
    real_model_report_metadata,
    real_model_skip_reason,
)
from harness.stack import EvalStack  # noqa: E402

logger = logging.getLogger(__name__)


def run_regressions(report: dict[str, Any]) -> None:
    """Proportionate Stage A/B regression suites (read-only on runtime code)."""
    sections: list[dict[str, Any]] = []

    def run_cmd(name: str, cmd: list[str], *, cwd: Path) -> dict[str, Any]:
        started = time.monotonic()
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        skipped = proc.returncode == 2 and name == "container_isolation_script"
        return {
            "name": name,
            "command": " ".join(cmd),
            "exit_code": proc.returncode,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "stdout_tail": proc.stdout.splitlines()[-8:],
            "stderr_tail": proc.stderr.splitlines()[-8:],
            "pass": proc.returncode == 0,
            "skip": skipped,
            "skip_reason": "container engine unavailable (Stage B waiver on record)" if skipped else None,
        }

    sections.append(
        run_cmd(
            "stage_a_validate_kit",
            [sys.executable, "scripts/validate_kit.py"],
            cwd=EVAL_DIR,
        )
    )
    sections.append(
        run_cmd(
            "stage_a_grader_tests",
            [sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"],
            cwd=EVAL_DIR,
        )
    )
    agent_python = REPO_ROOT / "agent-service" / ".venv" / "bin" / "python"
    if agent_python.is_file():
        sections.append(
            run_cmd(
                "agent_unit_tests",
                [str(agent_python), "-m", "pytest", "tests", "-q", "--ignore=tests/test_live_records_integration.py"],
                cwd=REPO_ROOT / "agent-service",
            )
        )
    records_python = REPO_ROOT / "records-mcp" / ".venv" / "bin" / "python"
    if records_python.is_file():
        sections.append(
            run_cmd(
                "records_unit_tests",
                [str(records_python), "-m", "pytest", "tests", "-q", "--ignore=tests/test_container.py"],
                cwd=REPO_ROOT / "records-mcp",
            )
        )
        container_script = REPO_ROOT / "records-mcp" / "scripts" / "verify_container_isolation.sh"
        if container_script.is_file():
            sections.append(
                run_cmd(
                    "container_isolation_script",
                    ["bash", str(container_script)],
                    cwd=REPO_ROOT / "records-mcp",
                )
            )
    report["regressions"] = sections


async def run_case_suite(
    *,
    cases_path: Path,
    agent_base: str,
    split_label: str,
    trials: int,
) -> dict[str, Any]:
    cases = load_cases(cases_path)
    trial_reports: list[dict[str, Any]] = []
    observations_path = EVAL_DIR / "var" / "evaluation" / f"observations_{split_label}.jsonl"
    observations_path.parent.mkdir(parents=True, exist_ok=True)

    for trial in range(trials):
        observations: list[dict[str, Any]] = []
        for case in cases:
            suffix = f"t{trial + 1}" if trials > 1 else ""
            obs = await run_case(case, agent_base=agent_base, suffix=suffix)
            as_of = date.fromisoformat(case["request"]["as_of"])
            fixture = REPO_ROOT / case["patient_fixture"]
            obs["baseline_compare"] = compare_baseline_adaptive(
                patient_fixture=fixture,
                as_of=as_of,
                tool_calls=obs.get("tool_calls") or [],
            )
            grade_report = grade(case, {k: obs[k] for k in ("case_id", "http_status", "profile", "tool_calls")})
            obs["structural_pass"] = grade_report["structural_pass"]
            obs["grade_errors"] = grade_report.get("errors", [])
            observations.append(obs)
        observations_path.write_text(
            "\n".join(json.dumps(row) for row in observations) + "\n",
            encoding="utf-8",
        )
        passed = sum(1 for row in observations if row.get("structural_pass"))
        failed = sum(1 for row in observations if not row.get("structural_pass"))
        trial_reports.append(
            {
                "trial": trial + 1,
                "cases": len(cases),
                "structural_pass": passed,
                "structural_fail": failed,
                "observations_path": str(observations_path),
                "observations": observations,
            }
        )
    return {"split": split_label, "trials": trial_reports}


def per_case_summary(suite: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten trial observations into per-case rows."""
    if suite.get("status") == "skipped" or not suite.get("trials"):
        return []
    trial = suite["trials"][-1]
    rows_out: list[dict[str, Any]] = []
    for obs in trial.get("observations", []):
        rows_out.append(
            {
                "case_id": obs["case_id"],
                "structural_pass": obs.get("structural_pass"),
                "http_status": obs.get("http_status"),
                "grade_errors": obs.get("grade_errors", []),
                "latency_ms": (obs.get("metrics") or {}).get("latency_ms"),
                "model_calls": (obs.get("metrics") or {}).get("model_calls"),
                "tool_attempts": (obs.get("metrics") or {}).get("tool_attempts"),
            }
        )
    return rows_out


async def main_async(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report_dir = EVAL_DIR / "reports" / "stage_c"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    report: dict[str, Any] = {
        "stage": "C",
        "timestamp_utc": stamp,
        "independence": "unavailable_single_agent_sequential_roles",
        "clinical_review": "pending",
        "clinical_validation": "not_established",
        "candidate_holdout_tuning": "not_used",
        "real_model": {},
        "suites": {},
        "extensions": {},
        "defects_routed": [],
        "per_case": {},
        "acceptance_verdict": "blocked",
    }

    stub_only = args.stub_only
    if not stub_only:
        run_regressions(report)
    else:
        report["regressions"] = [{"name": "stub_only_rerun", "pass": True, "skip": True, "skip_reason": "dev stub rerun"}]
    regression_fail = sum(1 for item in report["regressions"] if not item["pass"] and not item.get("skip"))

    stack = EvalStack()
    agent_db = EVAL_DIR / "var" / "evaluation" / f"agent_stage_c_{stamp}.sqlite3"
    demo_sessions = HARNESS_DIR / "config" / "demo_sessions_eval.json"
    mcp_registry = HARNESS_DIR / "config" / "mcp_servers_eval.json"
    signing_key = HARNESS_DIR / "config" / "secrets" / "mcp-signing-key.pem"

    try:
        stack.start(
            agent_db=agent_db,
            demo_sessions=demo_sessions,
            mcp_registry=mcp_registry,
            enable_extension_tools=not stub_only,
            start_ping=not stub_only,
        )
        os.environ["EVAL_TRACE_FILE"] = str(EVAL_DIR / "var" / "evaluation" / "tool_trace.jsonl")
        report["agent_test_fault_file"] = str(getattr(stack, "fault_file", ""))

        if not stub_only:
            report["extensions"]["registry"] = prove_registry_load_without_coordinator_change()
            report["extensions"]["get_record_counts"] = await prove_get_record_counts(
                mcp_url=f"http://127.0.0.1:{stack.mcp_port}/mcp",
                signing_key=signing_key,
            )
            report["extensions"]["ping"] = await prove_ping_server(
                ping_url=f"http://127.0.0.1:{stack.ping_port}/mcp",
                signing_key=signing_key,
            )

        stub_dev = await run_case_suite(
            cases_path=EVAL_DIR / "cases" / "dev.jsonl",
            agent_base=stack.agent_base,
            split_label="dev_stub",
            trials=1,
        )
        report["suites"]["dev_stub_http_mcp"] = stub_dev
        report["per_case"]["dev_stub"] = per_case_summary(stub_dev)

        dev_all_pass = stub_dev["trials"][-1]["structural_fail"] == 0
        run_holdout = dev_all_pass if stub_only else True
        if run_holdout:
            holdout = await run_case_suite(
                cases_path=EVAL_DIR / "cases" / "candidate_holdout.jsonl",
                agent_base=stack.agent_base,
                split_label="holdout_stub",
                trials=1,
            )
            report["suites"]["candidate_holdout_stub_http_mcp"] = holdout
            report["per_case"]["holdout_stub"] = per_case_summary(holdout)
        else:
            report["suites"]["candidate_holdout_stub_http_mcp"] = {
                "status": "skipped",
                "reason": "dev stub cases did not all pass; holdout not run (stub-only gate)",
            }
            report["per_case"]["holdout_stub"] = []

        if not stub_only and real_model_configured():
            backend = os.environ["MODEL_BACKEND"]
            os.environ["EVAL_MODEL_BACKEND"] = backend
            stack.stop()
            stack = EvalStack()
            stack.start(
                agent_db=EVAL_DIR / "var" / "evaluation" / f"agent_stage_c_real_model_{stamp}.sqlite3",
                demo_sessions=demo_sessions,
                mcp_registry=mcp_registry,
                enable_extension_tools=True,
                start_ping=False,
            )
            real_model_dev = await run_case_suite(
                cases_path=EVAL_DIR / "cases" / "dev.jsonl",
                agent_base=stack.agent_base,
                split_label="dev_real_model",
                trials=3,
            )
            report["suites"]["dev_real_model"] = real_model_dev
            report["real_model"] = real_model_report_metadata(status="executed")
            report["real_model"]["trials_per_case"] = 3
        elif not stub_only:
            report["real_model"] = real_model_report_metadata(status="skipped")
            report["real_model"]["reason"] = real_model_skip_reason()
            report["suites"]["dev_real_model"] = {"status": "skipped"}
        else:
            report["real_model"] = real_model_report_metadata(status="skipped")
            report["real_model"]["reason"] = "stub-only rerun; real model not executed"

    finally:
        stack.stop()

    for label in ("dev_stub", "holdout_stub"):
        for row in report.get("per_case", {}).get(label, []):
            if row.get("structural_pass"):
                continue
            report["defects_routed"].append(
                {
                    "owner": "agent builder",
                    "id": f"CASE-{row['case_id']}",
                    "summary": f"{row['case_id']} structural fail: {', '.join(row.get('grade_errors') or [])}",
                }
            )

    def summarize_suite(suite: dict[str, Any]) -> dict[str, int]:
        if suite.get("status") == "skipped":
            return {"pass": 0, "fail": 0, "skip": 1}
        trial = suite["trials"][-1]
        return {
            "pass": trial["structural_pass"],
            "fail": trial["structural_fail"],
            "skip": 0,
            "cases": trial["cases"],
        }

    counts = {
        "regressions": {
            "pass": sum(1 for item in report["regressions"] if item["pass"]),
            "fail": regression_fail,
            "skip": sum(1 for item in report["regressions"] if item.get("skip")),
        },
        "extensions": {
            "pass": sum(1 for item in report["extensions"].values() if item.get("pass")),
            "fail": sum(1 for item in report["extensions"].values() if not item.get("pass")),
            "skip": 0,
        },
        "dev_stub": summarize_suite(report["suites"]["dev_stub_http_mcp"]),
        "holdout_stub": summarize_suite(report["suites"]["candidate_holdout_stub_http_mcp"]),
        "real_model": summarize_suite(report["suites"].get("dev_real_model", {"status": "skipped"})),
    }
    if report["suites"]["candidate_holdout_stub_http_mcp"].get("status") == "skipped":
        counts["holdout_stub"] = {"pass": 0, "fail": 0, "skip": 1, "cases": 8}

    extension_ok = not report["extensions"] or all(item.get("pass") for item in report["extensions"].values())
    stub_ok = counts["dev_stub"]["fail"] == 0 and counts["holdout_stub"]["fail"] == 0
    regressions_ok = regression_fail == 0
    real_model_ok = report["real_model"]["status"] != "executed" or counts["real_model"]["fail"] == 0

    if (
        regressions_ok
        and extension_ok
        and stub_ok
        and real_model_ok
        and report["real_model"]["status"] != "skipped"
    ):
        report["acceptance_verdict"] = "pass_pending_human"
    elif regressions_ok and extension_ok:
        report["acceptance_verdict"] = "fail_with_evidence"
    else:
        report["acceptance_verdict"] = "blocked"

    report["stage_b_container_regression"] = next(
        (item for item in report["regressions"] if item["name"] == "container_isolation_script"),
        None,
    )

    report["counts"] = counts
    out_path = report_dir / f"stage_c_report_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    summary_path = report_dir / "stage_c_latest.json"
    summary_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({"report": str(out_path), "counts": counts, "verdict": report["acceptance_verdict"]}, indent=2))
    return 0 if report["acceptance_verdict"] == "pass_pending_human" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Stage C evaluation harness")
    parser.add_argument(
        "--stub-only",
        action="store_true",
        help="Run stub HTTP/MCP cases only; run holdout once if all 12 dev cases pass",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
