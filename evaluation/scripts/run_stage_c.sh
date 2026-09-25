#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${ROOT}/agent-service/.venv/bin/python"
exec "${PYTHON}" "${ROOT}/evaluation/harness/run_stage_c.py" "$@"
