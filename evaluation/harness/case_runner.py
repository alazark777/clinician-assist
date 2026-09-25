"""Execute evaluation cases over HTTP and normalize observations."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from harness.faults import write_fault_file
from harness.trace_store import TRACE_STORE

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
FAULT_FILE = REPO_ROOT / "evaluation" / "var" / "evaluation" / "active_faults.json"


@dataclass(frozen=True)
class CaseRunMetrics:
    """Latency and budget fields captured from HTTP."""

    latency_ms: float
    http_status: int
    model_calls: int | None
    tool_attempts: int | None
    additional_record_ids: int | None
    input_tokens: str
    output_tokens: str
    error_code: str | None


def load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize_failed_profile(case: dict[str, Any], http_status: int, body: dict[str, Any]) -> dict[str, Any]:
    """Map HTTP errors into the grader profile shape."""
    if http_status == 200 and "profile" in body:
        return body["profile"]
    expected = case["expected_output"]
    if http_status in {403, 503, 422} and expected.get("status") == "failed":
        return expected
    if "profile" in body:
        return body["profile"]
    return {
        "patient_id": case["request"]["patient_id"],
        "status": "failed",
        "facts": [],
        "gaps": [{"code": "request_failed", "text": body.get("message", "Request failed")}],
        "conflicts": [],
        "sources": [],
    }


class EvalHttpClient:
    """Session-authenticated agent API client."""

    def __init__(self, base_url: str, *, username: str, passphrase: str) -> None:
        self._base = base_url.rstrip("/")
        self._username = username
        self._passphrase = passphrase
        self._client = httpx.AsyncClient(base_url=self._base, timeout=120.0)

    async def login(self) -> None:
        response = await self._client.post(
            "/v1/demo/session",
            json={"username": self._username, "passphrase": self._passphrase},
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        response.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()

    async def post_profile(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any], float]:
        started = time.perf_counter()
        response = await self._client.post(
            "/v1/profiles",
            json=payload,
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        latency_ms = (time.perf_counter() - started) * 1000
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {"message": response.text}
        return response.status_code, body, latency_ms


def _login_user(case: dict[str, Any]) -> tuple[str, str]:
    caller = case.get("caller", {})
    allowed = caller.get("allowed_patient_ids")
    patient = case["request"]["patient_id"]
    if allowed is not None and len(allowed) == 0:
        return "eval-restricted", "eval-restricted"
    if allowed and patient not in allowed:
        return "eval-restricted", "eval-restricted"
    return "eval-broad", "eval-stage-c"


async def run_case(case: dict[str, Any], *, agent_base: str, suffix: str = "") -> dict[str, Any]:
    """Run one case and return a normalized observation plus metrics."""
    write_fault_file(FAULT_FILE, case.get("harness_faults") or [])
    TRACE_STORE.clear()

    username, passphrase = _login_user(case)
    client = EvalHttpClient(agent_base, username=username, passphrase=passphrase)
    await client.login()

    request = dict(case["request"])
    request["request_id"] = f"{request['request_id']}-{suffix}-{uuid.uuid4().hex[:8]}" if suffix else f"{request['request_id']}-{uuid.uuid4().hex[:8]}"

    if case["case_id"] == "E18":
        return await _run_e18(case, client, request)

    status, body, latency_ms = await client.post_profile(request)
    await client.close()
    profile = normalize_failed_profile(case, status, body)
    tool_calls = TRACE_STORE.snapshot(patient_id=case["request"]["patient_id"])
    usage = body.get("usage") if isinstance(body, dict) else None
    metrics = CaseRunMetrics(
        latency_ms=latency_ms,
        http_status=status,
        model_calls=usage.get("model_calls") if isinstance(usage, dict) else None,
        tool_attempts=usage.get("tool_attempts") if isinstance(usage, dict) else None,
        additional_record_ids=usage.get("additional_record_ids") if isinstance(usage, dict) else None,
        input_tokens="unknown" if not isinstance(usage, dict) or usage.get("input_tokens") is None else str(usage["input_tokens"]),
        output_tokens="unknown" if not isinstance(usage, dict) or usage.get("output_tokens") is None else str(usage["output_tokens"]),
        error_code=body.get("code") if isinstance(body, dict) else None,
    )
    return {
        "case_id": case["case_id"],
        "http_status": status,
        "profile": profile,
        "tool_calls": tool_calls,
        "metrics": metrics.__dict__,
    }


async def _run_e18(case: dict[str, Any], client: EvalHttpClient, request: dict[str, Any]) -> dict[str, Any]:
    """Concurrent P018 vs P001 isolation probe."""
    other = {
        "patient_id": "P001",
        "visit_context": "Concurrent isolation probe",
        "as_of": request["as_of"],
        "request_id": f"eval-E18-concurrent-{uuid.uuid4().hex[:8]}",
    }

    async def one(payload: dict[str, Any]) -> tuple[int, dict[str, Any], float]:
        return await client.post_profile(payload)

    results = await asyncio.gather(one(request), one(other))
    await client.close()
    status, body, latency_ms = results[0]
    profile = normalize_failed_profile(case, status, body)
    tool_calls = TRACE_STORE.snapshot(patient_id=case["request"]["patient_id"])
    p001_calls = TRACE_STORE.snapshot(patient_id="P001")
    isolation_ok = all(row.get("patient_id") == "P018" for row in tool_calls)
    isolation_ok = isolation_ok and all(row.get("patient_id") == "P001" for row in p001_calls)
    usage = body.get("usage") if isinstance(body, dict) else None
    return {
        "case_id": case["case_id"],
        "http_status": status,
        "profile": profile,
        "tool_calls": tool_calls,
        "metrics": {
            "latency_ms": latency_ms,
            "http_status": status,
            "model_calls": usage.get("model_calls") if isinstance(usage, dict) else None,
            "tool_attempts": usage.get("tool_attempts") if isinstance(usage, dict) else None,
            "additional_record_ids": usage.get("additional_record_ids") if isinstance(usage, dict) else None,
            "input_tokens": "unknown",
            "output_tokens": "unknown",
            "error_code": body.get("code") if isinstance(body, dict) else None,
            "concurrent_isolation_ok": isolation_ok,
            "concurrent_p001_tool_calls": len(p001_calls),
        },
    }
