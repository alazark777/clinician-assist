"""Optional container isolation checks."""

from __future__ import annotations

import subprocess

import pytest

from container_runtime import (
    compose_service_container_id,
    engine_argv,
    resolve_container_engine,
    skip_reason_no_engine,
)

COMPOSE_FILE = "compose.yaml"
SERVICE_NAME = "records-mcp"


@pytest.fixture(scope="module")
def container_engine():
    """Resolve docker, podman, or CONTAINER_CMD with a live engine service."""
    engine = resolve_container_engine()
    if engine is None:
        pytest.skip(skip_reason_no_engine())
    return engine


def test_container_mount_isolation(container_engine) -> None:
    """Prove the running container only exposes the patient mount."""
    container_id = compose_service_container_id(
        container_engine,
        compose_file=COMPOSE_FILE,
        service_name=SERVICE_NAME,
    )
    if container_id is None:
        pytest.skip(
            f"{container_engine.cmd} compose: {SERVICE_NAME} is not running; "
            f"start with `{container_engine.cmd} compose -f {COMPOSE_FILE} up --build -d`"
        )

    mounts = subprocess.run(
        engine_argv(
            container_engine,
            "inspect",
            "-f",
            "{{json .Mounts}}",
            container_id,
        ),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "patients" in mounts.stdout
    assert "evaluation" not in mounts.stdout
    assert "agent" not in mounts.stdout.lower()

    write_attempt = subprocess.run(
        engine_argv(
            container_engine,
            "exec",
            container_id,
            "sh",
            "-c",
            "touch /data/patients/.write-test",
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert write_attempt.returncode != 0

    host_config = subprocess.run(
        engine_argv(
            container_engine,
            "inspect",
            "-f",
            "{{.HostConfig.ReadonlyRootfs}}",
            container_id,
        ),
        capture_output=True,
        text=True,
        check=True,
    )
    assert host_config.stdout.strip().lower() == "true"

    user = subprocess.run(
        engine_argv(
            container_engine,
            "inspect",
            "-f",
            "{{.Config.User}}",
            container_id,
        ),
        capture_output=True,
        text=True,
        check=True,
    )
    assert user.stdout.strip() == "records"
