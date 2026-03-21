#!/usr/bin/env bash
set -euo pipefail

CHARTS=("helm/minimalist" "helm/k8s-lite")
TMP_OUT="/tmp/helm_template_out.yaml"
ERRORS=0

echo "Helm Vault/template validator - checking required labels and Vault references"

for CHART in "${CHARTS[@]}"; do
  echo "\nValidating chart: $CHART"
  if [ ! -d "$CHART" ]; then
    echo "  Chart path not found: $CHART"
    ERRORS=$((ERRORS+1))
    continue
  fi

  if ! helm template "$CHART" > "$TMP_OUT" 2>/tmp/helm_template_err || [ ! -s "$TMP_OUT" ]; then
    echo "  helm template failed for $CHART"
    cat /tmp/helm_template_err || true
    ERRORS=$((ERRORS+1))
    continue
  fi

  # Ensure Deployments/Jobs include app and version labels in metadata.labels
  MISSING_LABELS=0
  # Identify lines where kind: Deployment or kind: Job appears, inspect nearby metadata.labels
  grep -n -E "^kind: (Deployment|Job)" "$TMP_OUT" | cut -d: -f1 | while read -r LINENO; do
    BLOCK=$(tail -n +"$LINENO" "$TMP_OUT" | head -n 40)
    echo "$BLOCK" | sed -n '1,40p' > /tmp/_block.yaml
    if ! grep -q "labels:" /tmp/_block.yaml || ! grep -q "app:" /tmp/_block.yaml || ! grep -q "version:" /tmp/_block.yaml; then
      echo "  Resource starting at line $LINENO is missing 'app' and/or 'version' labels"
      MISSING_LABELS=1
    fi
  done

  if [ "$MISSING_LABELS" -eq 1 ]; then
    echo "  Label validation failed for $CHART"
    ERRORS=$((ERRORS+1))
  else
    echo "  Labels present for Deployments/Jobs in $CHART"
  fi

  # If chart enables Vault in values.yaml, ensure templates reference podinfo or vault
  if [ -f "$CHART/values.yaml" ] && grep -q "vault" "$CHART/values.yaml" && grep -q "enabled:[[:space:]]*true" "$CHART/values.yaml"; then
    if ! grep -q "podinfo" "$TMP_OUT" && ! grep -q "vault" "$TMP_OUT"; then
      echo "  Chart $CHART enables Vault in values.yaml but templates lack podinfo/vault references"
      ERRORS=$((ERRORS+1))
    else
      echo "  Vault references found in templates for $CHART"
    fi
  else
    echo "  Vault not explicitly enabled in $CHART/values.yaml or values file missing; skipping vault-specific checks"
  fi
done

if [ "$ERRORS" -ne 0 ]; then
  echo "\nValidation completed: $ERRORS error(s) found"
  exit 2
fi

echo "\nValidation passed for all checked charts"
exit 0
