"""Resolve a working Docker or Podman CLI for compose-based isolation checks."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContainerEngine:
    """A container CLI verified against a running engine service."""

    cmd: str


def _engine_service_ready(cmd: str) -> tuple[bool, str]:
    """Return whether ``cmd info`` succeeds and a short diagnostic snippet."""
    if shutil.which(cmd) is None:
        return False, f"{cmd} binary not found on PATH"
    proc = subprocess.run(
        [cmd, "info"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return True, ""
    detail = (proc.stderr or proc.stdout or "").strip().splitlines()
    snippet = detail[0] if detail else f"{cmd} info exited {proc.returncode}"
    return False, snippet


def resolve_container_engine() -> ContainerEngine | None:
    """Pick CONTAINER_CMD or the first of docker/podman with a live service."""
    override = os.environ.get("CONTAINER_CMD", "").strip()
    candidates: tuple[str, ...]
    if override:
        candidates = (override,)
    else:
        candidates = ("docker", "podman")

    for cmd in candidates:
        ready, _ = _engine_service_ready(cmd)
        if ready:
            return ContainerEngine(cmd=cmd)
    return None


def skip_reason_no_engine() -> str:
    """Human-readable skip reason when no engine is usable."""
    override = os.environ.get("CONTAINER_CMD", "").strip()
    if override:
        ready, detail = _engine_service_ready(override)
        if not ready:
            return (
                f"CONTAINER_CMD={override!r} is set but the engine service is "
                f"unavailable: {detail}"
            )
    docker_ready, docker_detail = _engine_service_ready("docker")
    podman_ready, podman_detail = _engine_service_ready("podman")
    parts = [
        "no container engine with a running service is available "
        "(set CONTAINER_CMD or start Docker/Podman)"
    ]
    if shutil.which("docker") is not None and not docker_ready:
        parts.append(f"docker: {docker_detail}")
    if shutil.which("podman") is not None and not podman_ready:
        parts.append(f"podman: {podman_detail}")
    return "; ".join(parts)


def compose_argv(engine: ContainerEngine, *args: str) -> list[str]:
    """Build ``engine compose …`` argument lists."""
    return [engine.cmd, "compose", *args]


def engine_argv(engine: ContainerEngine, *args: str) -> list[str]:
    """Build ``engine …`` argument lists (inspect, exec, etc.)."""
    return [engine.cmd, *args]


def compose_service_container_id(
    engine: ContainerEngine,
    *,
    compose_file: str,
    service_name: str,
) -> str | None:
    """Return a running container ID for a compose service, if any."""
    direct = subprocess.run(
        compose_argv(
            engine,
            "-f",
            compose_file,
            "ps",
            "-q",
            service_name,
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    if direct.returncode == 0:
        candidate = direct.stdout.strip().splitlines()
        if candidate:
            return candidate[0]

    for label_key in (
        "com.docker.compose.service",
        "io.podman.compose.service",
    ):
        labeled = subprocess.run(
            engine_argv(
                engine,
                "ps",
                "-q",
                "--filter",
                f"label={label_key}={service_name}",
                "--filter",
                "status=running",
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        if labeled.returncode == 0:
            candidate = labeled.stdout.strip().splitlines()
            if candidate:
                return candidate[0]

    by_name = subprocess.run(
        engine_argv(
            engine,
            "ps",
            "-q",
            "--filter",
            f"name={service_name}",
            "--filter",
            "status=running",
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    if by_name.returncode == 0:
        candidate = by_name.stdout.strip().splitlines()
        if candidate:
            return candidate[0]

    all_ids = subprocess.run(
        compose_argv(engine, "-f", compose_file, "ps", "-q"),
        capture_output=True,
        text=True,
        check=False,
    )
    if all_ids.returncode != 0:
        return None

    for container_id in all_ids.stdout.strip().splitlines():
        if not container_id:
            continue
        status = subprocess.run(
            engine_argv(
                engine,
                "inspect",
                "-f",
                "{{.State.Running}}",
                container_id,
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        if status.returncode != 0 or status.stdout.strip().lower() != "true":
            continue
        name = subprocess.run(
            engine_argv(
                engine,
                "inspect",
                "-f",
                "{{.Name}}",
                container_id,
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        if name.returncode != 0:
            continue
        normalized = name.stdout.strip().lstrip("/")
        if service_name in normalized:
            return container_id
    return None
