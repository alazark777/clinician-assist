#!/usr/bin/env bash
# Delete local telemetry files older than RETENTION_DAYS (default 7).
set -euo pipefail

KIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TARGET="${KIT_ROOT}/var/telemetry/agent-jaeger"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

if [[ ! -d "${TARGET}" ]]; then
  echo "Nothing to prune (${TARGET} missing)"
  exit 0
fi

find "${TARGET}" -type f -mtime +"${RETENTION_DAYS}" -print -delete
echo "Pruned files under ${TARGET} older than ${RETENTION_DAYS} days"
