#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
uv sync --group dev
uv run pytest -q
uv run python3 scripts/validate_redaction.py
scripts/validate_collector_config.sh || test $? -eq 2
