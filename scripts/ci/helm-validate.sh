#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/../.." && pwd -P)
echo "Ensuring required helm repos (bitnami) are present..."
helm repo add bitnami https://charts.bitnami.com/bitnami || true
helm repo update || true

echo "Running helm dependency build for helm/minimalist..."
helm dependency build "$ROOT_DIR/helm/minimalist" || true

echo "Running helm-template validator"
bash "$ROOT_DIR/scripts/validate-helm-vault.sh"

echo "CI helm validation completed"
