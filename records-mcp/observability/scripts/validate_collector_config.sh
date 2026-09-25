#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "${ROOT}/images.env"

CONFIG="${ROOT}/otel-collector.yaml"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found; skip collector validate (config path: ${CONFIG})" >&2
  exit 2
fi

docker run --rm \
  -v "${CONFIG}:/etc/otelcol/config.yaml:ro" \
  "${OTEL_COLLECTOR_IMAGE}" \
  validate --config=/etc/otelcol/config.yaml

echo "Collector config valid: ${CONFIG}"
