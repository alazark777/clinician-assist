"""Start and stop Stage C runtime processes (evaluator-owned orchestration)."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from harness.model_config import apply_agent_model_env

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = Path(__file__).resolve().parent
EVAL_SECRETS = HARNESS_DIR / "config" / "secrets"
AGENT_DIR = REPO_ROOT / "agent-service"
RECORDS_DIR = REPO_ROOT / "records-mcp"


@dataclass
class ManagedProcess:
    """One subprocess with teardown."""

    name: str
    popen: subprocess.Popen[bytes]
    log_path: Path

    def stop(self) -> None:
        """Terminate gracefully."""
        if self.popen.poll() is not None:
            return
        self.popen.send_signal(signal.SIGTERM)
        try:
            self.popen.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.popen.kill()


@dataclass
class EvalStack:
    """Instrumented MCP + agent API for evaluation."""

    processes: list[ManagedProcess] = field(default_factory=list)
    agent_base: str = "http://127.0.0.1:8000"
    mcp_port: int = 8010
    ping_port: int = 8012
    fault_file: Path | None = None

    def start(
        self,
        *,
        agent_db: Path,
        demo_sessions: Path,
        mcp_registry: Path,
        enable_extension_tools: bool = False,
        start_ping: bool = False,
    ) -> None:
        """Launch eval MCP and agent API."""
        var_dir = REPO_ROOT / "evaluation" / "var" / "evaluation"
        var_dir.mkdir(parents=True, exist_ok=True)
        fault_file = (var_dir / "active_faults.json").resolve()
        if not fault_file.exists():
            fault_file.write_text('{"harness_faults": []}', encoding="utf-8")
        self.fault_file = fault_file

        mcp_env = os.environ.copy()
        mcp_env.update(
            {
                "MCP_PORT": str(self.mcp_port),
                "PATIENT_DATA_DIR": str(RECORDS_DIR / "data" / "patients"),
                "MCP_VERIFICATION_KEY": str(EVAL_SECRETS / "mcp-verification-key.pem"),
                "MCP_TOKEN_ISSUER": "clinician-agent-api",
                "MCP_TOKEN_AUDIENCE": "clinician-records-mcp",
                "MCP_ALLOWED_ORIGINS": "http://127.0.0.1:8000",
                "EVAL_FAULT_FILE": str(fault_file),
                "EVAL_TRACE_FILE": str(var_dir / "tool_trace.jsonl"),
                "OTEL_EXPORTER_OTLP_ENDPOINT": "",
                "ENABLE_EXTENSION_TOOLS": "true" if enable_extension_tools else "false",
            }
        )
        mcp_log = var_dir / "instrumented_mcp.log"
        records_python = RECORDS_DIR / ".venv" / "bin" / "python"
        if not records_python.is_file():
            records_python = Path(sys.executable)
        self.processes.append(
            self._spawn(
                "instrumented-mcp",
                [str(records_python), str(HARNESS_DIR / "instrumented_mcp_main.py")],
                mcp_env,
                mcp_log,
            )
        )
        self._wait_http(f"http://127.0.0.1:{self.mcp_port}/mcp", timeout=45)

        if start_ping:
            ping_env = mcp_env.copy()
            ping_env.update(
                {
                    "MCP_PING_PORT": str(self.ping_port),
                    "MCP_TOKEN_AUDIENCE": "clinician-eval-ping-mcp",
                    "MCP_VERIFICATION_KEY": str(EVAL_SECRETS / "mcp-verification-key.pem"),
                }
            )
            ping_log = var_dir / "ping_mcp.log"
            self.processes.append(
                self._spawn(
                    "ping-mcp",
                    [str(records_python), str(HARNESS_DIR / "ping_mcp_main.py")],
                    ping_env,
                    ping_log,
                )
            )
            self._wait_http(f"http://127.0.0.1:{self.ping_port}/mcp", timeout=45)

        agent_env = os.environ.copy()
        agent_env.update(
            {
                "APP_ENV": "local",
                "MODEL_ID": os.environ.get("MODEL_ID", "offline-stub"),
                "MCP_REGISTRY_PATH": str(mcp_registry),
                "MCP_SIGNING_KEY_PATH": str(EVAL_SECRETS / "mcp-signing-key.pem"),
                "DEMO_SESSIONS_PATH": str(demo_sessions),
                "AGENT_DB_PATH": str(agent_db),
                "AGENT_TEST_FAULT_FILE": str(fault_file),
                "OTEL_EXPORTER_OTLP_ENDPOINT": "",
            }
        )
        apply_agent_model_env(agent_env)
        agent_log = var_dir / "agent_api.log"
        agent_python = AGENT_DIR / ".venv" / "bin" / "python"
        if not agent_python.is_file():
            agent_python = Path(sys.executable)
        agent_env["PYTHONPATH"] = str(AGENT_DIR / "src")
        self.processes.append(
            self._spawn(
                "agent-api",
                [
                    str(agent_python),
                    "-m",
                    "uvicorn",
                    "clinician_agent.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ],
                agent_env,
                agent_log,
                cwd=AGENT_DIR,
            )
        )
        self._wait_http(f"{self.agent_base}/health/live", timeout=45)

    def stop(self) -> None:
        """Stop all managed processes."""
        for proc in reversed(self.processes):
            proc.stop()

    @staticmethod
    def _spawn(
        name: str,
        cmd: list[str],
        env: dict[str, str],
        log_path: Path,
        cwd: Path | None = None,
    ) -> ManagedProcess:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("ab")
        logger.info("Starting %s: %s", name, " ".join(cmd))
        popen = subprocess.Popen(
            cmd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=str(cwd) if cwd else None,
        )
        return ManagedProcess(name=name, popen=popen, log_path=log_path)

    @staticmethod
    def _wait_http(url: str, *, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with httpx.Client(timeout=2.0) as client:
                    response = client.get(url)
                    if response.status_code < 500:
                        return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            time.sleep(0.4)
        raise RuntimeError(f"Timed out waiting for {url}: {last_error}")
