#!/usr/bin/env bash
# Verify hardened records-mcp mount isolation against a running compose stack.
# Honors CONTAINER_CMD or auto-detects docker/podman when the engine service responds.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

COMPOSE_FILE="compose.yaml"
SERVICE_NAME="records-mcp"

engine_ready() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    return 1
  fi
  "${cmd}" info >/dev/null 2>&1
}

resolve_engine() {
  if [[ -n "${CONTAINER_CMD:-}" ]]; then
    if engine_ready "${CONTAINER_CMD}"; then
      printf '%s' "${CONTAINER_CMD}"
      return 0
    fi
    echo "CONTAINER_CMD=${CONTAINER_CMD} is set but the engine service is unavailable" >&2
    return 1
  fi
  if engine_ready docker; then
    printf '%s' "docker"
    return 0
  fi
  if engine_ready podman; then
    printf '%s' "podman"
    return 0
  fi
  echo "No container engine with a running service (set CONTAINER_CMD or start Docker/Podman)" >&2
  return 1
}

skip() {
  echo "SKIP: $*" >&2
  exit 2
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

ENGINE="$(resolve_engine)" || skip "container engine unavailable"

resolve_service_container_id() {
  local id=""
  id="$("${ENGINE}" compose -f "${COMPOSE_FILE}" ps -q "${SERVICE_NAME}" 2>/dev/null | head -n1 | tr -d '[:space:]')"
  if [[ -n "${id}" ]]; then
    printf '%s' "${id}"
    return 0
  fi
  id="$("${ENGINE}" ps -q \
    --filter "label=com.docker.compose.service=${SERVICE_NAME}" \
    --filter "status=running" 2>/dev/null | head -n1 | tr -d '[:space:]')"
  if [[ -n "${id}" ]]; then
    printf '%s' "${id}"
    return 0
  fi
  id="$("${ENGINE}" ps -q \
    --filter "label=io.podman.compose.service=${SERVICE_NAME}" \
    --filter "status=running" 2>/dev/null | head -n1 | tr -d '[:space:]')"
  if [[ -n "${id}" ]]; then
    printf '%s' "${id}"
    return 0
  fi
  while read -r candidate; do
    [[ -z "${candidate}" ]] && continue
    if [[ "$("${ENGINE}" inspect -f '{{.State.Running}}' "${candidate}" 2>/dev/null)" == "true" ]]; then
      name="$("${ENGINE}" inspect -f '{{.Name}}' "${candidate}" 2>/dev/null | tr -d '/')"
      if [[ "${name}" == *"${SERVICE_NAME}"* ]]; then
        printf '%s' "${candidate}"
        return 0
      fi
    fi
  done < <("${ENGINE}" compose -f "${COMPOSE_FILE}" ps -q 2>/dev/null)
  return 1
}

container_id="$(resolve_service_container_id || true)"
if [[ -z "${container_id}" ]]; then
  skip "${SERVICE_NAME} is not running; start with: ${ENGINE} compose -f ${COMPOSE_FILE} up --build -d"
fi

mounts="$("${ENGINE}" inspect -f '{{json .Mounts}}' "${container_id}")"
echo "INFO: engine=${ENGINE} container=${container_id}"

case "${mounts}" in
  *patients*) ;;
  *) fail "patient mount not found in ${mounts}" ;;
esac
case "${mounts}" in
  *evaluation*) fail "evaluation mount must not be present: ${mounts}" ;;
esac
case "${mounts}" in
  *agent*) fail "agent mount must not be present: ${mounts}" ;;
esac

if "${ENGINE}" exec "${container_id}" sh -c "touch /data/patients/.write-test" >/dev/null 2>&1; then
  fail "write to read-only patient mount succeeded"
fi

readonly_root="$("${ENGINE}" inspect -f '{{.HostConfig.ReadonlyRootfs}}' "${container_id}")"
if [[ "${readonly_root}" != "true" ]]; then
  fail "expected ReadonlyRootfs=true, got ${readonly_root}"
fi

run_user="$("${ENGINE}" inspect -f '{{.Config.User}}' "${container_id}")"
if [[ "${run_user}" != "records" ]]; then
  fail "expected non-root user records, got ${run_user}"
fi

echo "PASS: mount isolation checks for ${SERVICE_NAME}"
