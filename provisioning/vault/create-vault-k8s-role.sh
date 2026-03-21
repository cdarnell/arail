#!/usr/bin/env bash
set -euo pipefail

# Create a Vault Kubernetes auth role that binds to given service accounts/namespaces
# Usage: create-vault-k8s-role.sh <role-name> <sa-names-comma> <namespaces-comma> <policies-comma>

ROLE_NAME=${1:-opencode-role}
SAS=${2:-opencode-sa}
NAMESPACES=${3:-opencode}
POLICIES=${4:-opencode-policy}
VAULT_ADDR=${VAULT_ADDR:-http://127.0.0.1:8200}

if [ -z "${VAULT_TOKEN:-}" ]; then
  echo "VAULT_TOKEN required in environment to write roles"
  exit 1
fi

echo "Creating Vault Kubernetes auth role '$ROLE_NAME'"
# Ensure service accounts exist in the target namespaces (create if missing)
OLDIFS=$IFS
IFS=',' read -ra SAS_ARR <<< "$SAS"
IFS=',' read -ra NS_ARR <<< "$NAMESPACES"
for ns in "${NS_ARR[@]}"; do
  for sa in "${SAS_ARR[@]}"; do
    kubectl create serviceaccount "$sa" -n "$ns" --dry-run=client -o yaml | kubectl apply -f - || true
  done
done
IFS=$OLDIFS

vault write auth/kubernetes/role/${ROLE_NAME} \
  bound_service_account_names=${SAS} \
  bound_service_account_namespaces=${NAMESPACES} \
  policies=${POLICIES} \
  ttl=24h || true

echo "Vault role created (or updated)."
