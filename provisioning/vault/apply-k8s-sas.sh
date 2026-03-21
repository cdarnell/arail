#!/usr/bin/env bash
set -euo pipefail

# Apply service account and namespace manifests for Vault-authenticated agents
K8S_DIR="$(dirname "$0")/k8s"

kubectl apply -f "$K8S_DIR/namespace-opencode.yaml"
kubectl apply -f "$K8S_DIR/opencode-serviceaccount.yaml"
kubectl apply -f "$K8S_DIR/zeroclaw-serviceaccount.yaml"

echo "Applied opencode & zeroclaw service accounts in namespace 'opencode'"
