#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_DIR="${ROOT}/secrets"
mkdir -p "${SECRETS_DIR}"

PRIVATE_KEY="${SECRETS_DIR}/mcp-signing-key.pem"
PUBLIC_KEY="${SECRETS_DIR}/mcp-verification-key.pem"

if [[ -f "${PRIVATE_KEY}" || -f "${PUBLIC_KEY}" ]]; then
  echo "Refusing to overwrite existing MCP key material in ${SECRETS_DIR}" >&2
  exit 1
fi

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "${PRIVATE_KEY}"
openssl rsa -in "${PRIVATE_KEY}" -pubout -out "${PUBLIC_KEY}"
chmod 600 "${PRIVATE_KEY}"
chmod 644 "${PUBLIC_KEY}"

echo "Wrote ${PRIVATE_KEY} and ${PUBLIC_KEY}"
