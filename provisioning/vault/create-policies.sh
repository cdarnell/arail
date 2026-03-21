#!/usr/bin/env bash
set -euo pipefail

# Apply all policies in provisioning/vault/policies via the Vault CLI
POL_DIR="$(dirname "$0")/policies"

if [ -z "${VAULT_ADDR:-}" ]; then
  echo "Please set VAULT_ADDR and VAULT_TOKEN environment variables before running this script."
  exit 1
fi

for p in "$POL_DIR"/*.hcl; do
  name=$(basename "$p" .hcl)
  echo "Writing policy: $name"
  vault policy write "$name" "$p"
done

echo "Policies applied."
