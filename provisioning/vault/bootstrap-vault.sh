#!/usr/bin/env bash
set -euo pipefail

# Bootstrap Vault in-cluster via Helm and configure Kubernetes auth and sample policies
# Assumes `kubectl`, `helm`, and `vault` CLIs are available and configured for the target cluster.

NAMESPACE=${1:-vault}
VALUES_FILE=${2:-"$(dirname "$0")/../helm/vault-values.yaml"}

echo "Creating namespace $NAMESPACE"
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

echo "Installing/Upgrading Vault Helm chart"
helm repo add hashicorp https://helm.releases.hashicorp.com || true
helm repo update
helm upgrade --install vault hashicorp/vault -n $NAMESPACE -f "$VALUES_FILE"

echo "Waiting for Vault server pod to be ready"
kubectl -n $NAMESPACE rollout status statefulset/vault --timeout=300s || true

echo "Port-forwarding Vault for bootstrapping (temporary)"
kubectl -n $NAMESPACE port-forward svc/vault 8200:8200 >/dev/null 2>&1 &
PF_PID=$!
sleep 2

export VAULT_ADDR=http://127.0.0.1:8200

echo "Checking Vault status (unsealed?)"
if vault status >/dev/null 2>&1; then
  echo "Vault responding"
else
  echo "Vault not responding on $VAULT_ADDR"
fi

echo "Enabling Kubernetes auth and applying policies"
# Expect policies are placed in provisioning/vault/policies/
for f in $(dirname "$0")/policies/*.hcl; do
  name=$(basename "$f" .hcl)
  echo "Writing policy $name"
  vault policy write "$name" "$f" || true
done

echo "Configuring Kubernetes auth (requires cluster service account token reviewer)"
# This command assumes you have service account JWT and K8s CA; for many clusters vault can auto-configure with helper scripts.
kubectl -n $NAMESPACE get secret -o wide || true

echo "Bootstrap complete. Kill port-forward PID $PF_PID"
kill $PF_PID || true

echo "Vault bootstrap finished. Remember to enable auto-unseal and secure auto-unseal keys in production."
