#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_DIR="${ROOT}/secrets"
mkdir -p "${SECRETS_DIR}"

PRIVATE_KEY="${SECRETS_DIR}/mcp-signing-key.pem"

if [[ -f "${PRIVATE_KEY}" ]]; then
  echo "Refusing to overwrite existing MCP signing key at ${PRIVATE_KEY}" >&2
  exit 1
fi

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "${PRIVATE_KEY}"
chmod 600 "${PRIVATE_KEY}"

cat <<EOF
Wrote ${PRIVATE_KEY}

Records MCP verifies RS256 tokens with the matching public key only.
Generate verification material in records-mcp (recommended):

  (cd ../records-mcp && ./scripts/generate_dev_keys.sh)

Then point this service at the shared private key:

  MCP_SIGNING_KEY_PATH=../records-mcp/secrets/mcp-signing-key.pem
EOF
