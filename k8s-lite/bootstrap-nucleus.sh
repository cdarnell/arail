#!/bin/bash
# THE NUCLEUS: Unified Bootstrap & Security Handshake
# Targets: Ubuntu / WSL / Cloud VM
# Goal: One-click prep for the Nucleus Academy Lab.
#
# This script consolidates pre-installation steps and the secure onboarding
# handshake required before deploying the lab with Helm.
#
# High-level actions (what this script documents and performs):
# - Optional package pre-install (system deps, K3s, kubectl symlink, Helm). Guarded
#   by the environment variable `PREINSTALL=1` to avoid unexpected package changes.
# - Hardware probe: runs `scripts/preinstall/hardware_probe.py` (if present)
#   to emit a tuned `values.generated.yaml` for the Helm chart.
# - Cluster checks: ensures K3s / kubectl are reachable and Linkerd status is
#   reported (Linkerd is optional but recommended for zero-trust posture).
# - Vault Kubernetes-auth bootstrap: if `VAULT_ADDR` and `VAULT_TOKEN` are set,
#   creates a `vault-auth` ServiceAccount and configures the Kubernetes auth
#   backend in Vault. Does not store any secret values in this repository.
# - Identity & RBAC: creates a minimal role `default-role` bound to the
#   `vault-auth` SA and a public read policy for `kv/data/public`.
# - Final output: prints a `helm install` command pointing at `./helm/k8s-lite`
#   with flags the operator should set (GPU-enabled, major focus, secret values).
#
# Security notes (read before running):
# - Do NOT put secret literals into this repo. Provide `VAULT_TOKEN`, `VAULT_ADDR`,
#   and other secrets via environment variables or a secret-management workflow
#   (Helm `--set-file` or Kubernetes Secrets).
# - The script will create a service-account-token secret if required by your
#   Kubernetes version. This is used only temporarily to register the token
#   with Vault's Kubernetes auth backend.
# - The script performs network calls to Vault and Kubernetes APIs. Ensure you
#   understand your network posture before proceeding.
#
# Usage:
#  PREINSTALL=1 ./bootstrap-nucleus.sh [OPENROUTER_API_KEY]
#
set -euo pipefail

# CLI flags
AUTO_DEPLOY=false
PREINSTALL=${PREINSTALL:-0}
HELM_RELEASE="nucleus"
NAMESPACE="default"

function usage() {
  cat <<EOF
Usage: $0 [OPTIONS] [OPENROUTER_API_KEY]

Options:
  --yes, --auto-deploy     Run 'helm install' automatically with the generated command
  --preinstall            Run system pre-install steps (apt, k3s, helm)
  --release NAME          Helm release name (default: nucleus)
  --namespace NAME        Kubernetes namespace for Helm release (default: default)
  -h, --help              Show this help

If OPENROUTER_API_KEY is provided as a positional arg, it will be injected
into the Helm command as the secret.openrouterKey value.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|--auto-deploy)
      AUTO_DEPLOY=true; shift;;
    --preinstall)
      PREINSTALL=1; shift;;
    --release)
      HELM_RELEASE="$2"; shift 2;;
    --namespace)
      NAMESPACE="$2"; shift 2;;
    -h|--help)
      usage; exit 0;;
    --*)
      echo "Unknown option: $1"; usage; exit 1;;
    *)
      # first non-option arg is API key
      if [ -z "${API_KEY-}" ]; then
        API_KEY="$1"
      fi
      shift;;
  esac
done

BOLD=$(tput bold 2>/dev/null || echo '')
NORMAL=$(tput sgr0 2>/dev/null || echo '')
GREEN=$(tput setaf 2 2>/dev/null || echo '')

echo "${BOLD}--- Welcome to the Nucleus Academy Onboarding ---${NORMAL}"

# -------------------------
# Step 0: Optional Pre-Install (system packages, k3s, helm)
# -------------------------
if [ "${PREINSTALL:-0}" = "1" ]; then
  echo "Running PREINSTALL steps (apt packages, k3s, helm)..."
  if [ "$EUID" -ne 0 ]; then
    echo "PREINSTALL requires root. Re-run with sudo or set PREINSTALL=0 to skip." >&2
    exit 1
  fi

  echo "Updating package lists and installing minimal dependencies..."
  apt-get update -y
  apt-get install -y curl sudo lsb-release libmagic-dev poppler-utils tesseract-ocr || true

  # Install K3s if not present
  if ! systemctl list-units --type=service | grep -q k3s; then
    echo "Installing K3s..."
    curl -sfL https://get.k3s.io | sh -s - --disable traefik
  else
    echo "K3s appears installed."
  fi

  # Ensure kubectl symlink exists for k3s
  if [ ! -f "/usr/local/bin/kubectl" ]; then
    echo "Creating kubectl symlink to K3s kubectl..."
    KDATA=(/var/lib/rancher/k3s/data/*)
    if [ -d "${KDATA[0]:-}" ]; then
      ln -sf "${KDATA[0]}/bin/kubectl" /usr/local/bin/kubectl || true
    fi
  fi

  # Install Helm if missing
  if ! command -v helm >/dev/null 2>&1; then
    echo "Installing Helm..."
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
  fi
fi

# -------------------------
# Step 1: Hardware & GPU Discovery
# -------------------------
echo "Step 1: Probing Hardware & GPU Availability..."
GPU_COUNT=0
if command -v kubectl >/dev/null 2>&1; then
  GPU_COUNT=$(kubectl get nodes -o jsonpath='{.items[0].status.allocatable.nvidia\.com/gpu}' 2>/dev/null || echo 0)
fi
if [ -n "$GPU_COUNT" ] && [ "$GPU_COUNT" -gt 0 ] 2>/dev/null; then
  echo "${GREEN}Found $GPU_COUNT NVIDIA GPU(s).${NORMAL} Enabling High-Performance AI profiles."
  GPU_FLAG="true"
else
  echo "No GPU detected. Falling back to CPU/OpenVINO optimization."
  GPU_FLAG="false"
fi

# -------------------------
# Step 2: Security Check (Linkerd)
# -------------------------
echo "Step 2: Checking Schoolhouse Security (Linkerd)..."
if command -v linkerd >/dev/null 2>&1; then
  if linkerd check >/dev/null 2>&1; then
    echo "Linkerd appears healthy."
  else
    echo "Warning: Linkerd check failed or Linkerd not fully installed. Consider installing linkerd for zero-trust mesh."
  fi
else
  echo "Linkerd CLI not found. Skipping Linkerd check.";
fi

# -------------------------
# Step 3: Vault Kubernetes-auth Handshake
# -------------------------
if [[ -n "${VAULT_ADDR:-}" && -n "${VAULT_TOKEN:-}" ]]; then
  echo "Step 3: Bootstrapping Vault Kubernetes-Auth..."

  kubectl create serviceaccount vault-auth -n kube-system --dry-run=client -o yaml | kubectl apply -f -
  kubectl create clusterrolebinding vault-auth-delegator --clusterrole=system:auth-delegator --serviceaccount=kube-system:vault-auth --dry-run=client -o yaml | kubectl apply -f -

  # Acquire SA token (K8s 1.24+ supports kubectl create token)
  SA_TOKEN=""
  if kubectl create token vault-auth -n kube-system >/dev/null 2>&1; then
    SA_TOKEN=$(kubectl create token vault-auth -n kube-system)
  else
    SECRET_NAME=$(kubectl get sa vault-auth -n kube-system -o jsonpath='{.secrets[0].name}' 2>/dev/null || true)
    if [ -n "$SECRET_NAME" ]; then
      SA_TOKEN=$(kubectl get secret "$SECRET_NAME" -n kube-system -o jsonpath='{.data.token}' | base64 --decode || true)
    fi
    if [ -z "$SA_TOKEN" ]; then
      echo "Creating service-account-token secret for vault-auth"
      kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: vault-auth-token
  namespace: kube-system
  annotations:
    kubernetes.io/service-account.name: vault-auth
type: kubernetes.io/service-account-token
EOF
      SECRET_NAME="vault-auth-token"
      # wait briefly for token population
      for i in 1 2 3 4 5; do
        SA_TOKEN=$(kubectl get secret "$SECRET_NAME" -n kube-system -o jsonpath='{.data.token}' 2>/dev/null | base64 --decode || true)
        [ -n "$SA_TOKEN" ] && break
        sleep 1
      done
    fi
  fi

  K8S_HOST=$(kubectl config view --raw -o jsonpath='{.clusters[0].cluster.server}')
  if [ -z "$K8S_HOST" ]; then
    echo "Failed to determine Kubernetes API server host; aborting Vault k8s config."
  else
    echo "Configuring Vault kubernetes auth backend"
    vault auth enable -path=${VAULT_AUTH_PATH:-kubernetes} kubernetes || true

    if [ -n "${SA_TOKEN}" ]; then
      vault write auth/${VAULT_AUTH_PATH:-kubernetes}/config \
        token_reviewer_jwt="$SA_TOKEN" \
        kubernetes_host="$K8S_HOST" || true
    else
      vault write auth/${VAULT_AUTH_PATH:-kubernetes}/config \
        kubernetes_host="$K8S_HOST" || true
    fi

    # Create public KV path + policy + role
    vault kv put kv/public hello=world || true
    cat > /tmp/public-read.hcl <<'EOF'
path "kv/data/public" {
  capabilities = ["read", "list"]
}
EOF
    vault policy write public-read /tmp/public-read.hcl || true
    vault write auth/${VAULT_AUTH_PATH:-kubernetes}/role/default-role \
      bound_service_account_names="vault-auth" \
      bound_service_account_namespaces="kube-system" \
      policies=public-read \
      ttl=24h || true

    echo "${GREEN}Vault Identity Bridge Established.${NORMAL}"
  fi
else
  echo "Step 3: Vault credentials missing. Skipping Security Handshake."
fi

# -------------------------
# Step 4: Optional Hardware Probe (auto-discovery of values.yaml)
# -------------------------
PROBE_PY="$(pwd)/scripts/preinstall/hardware_probe.py"
if [ -f "$PROBE_PY" ]; then
  echo "Running Pre-Install Hardware Probe (auto-discovery)..."
  if command -v python3 >/dev/null 2>&1; then
    python3 "$PROBE_PY" --output "$(pwd)/helm/k8s-lite/values.generated.yaml" || echo "Probe returned non-zero status.";
  elif command -v python >/dev/null 2>&1; then
    python "$PROBE_PY" --output "$(pwd)/helm/k8s-lite/values.generated.yaml" || echo "Probe returned non-zero status.";
  else
    echo "Python not found. Skipping hardware probe."
  fi
  echo "Hardware probe complete (if available)."
else
  echo "Hardware probe not found at scripts/preinstall/hardware_probe.py — skipping."
fi

# -------------------------
# Registry secrets & values generation
# - Create self-signed cert and htpasswd secret if not present
# - Emit helm/k8s-lite/values.registry.generated.yaml to enable registry in Helm
# -------------------------
function create_registry_secrets() {
  if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl not available; skipping registry secret creation.";
    return
  fi

  REG_TLS_SECRET=${REG_TLS_SECRET:-registry-tls}
  REG_HTPASS_SECRET=${REG_HTPASS_SECRET:-registry-htpasswd}
  VALUES_OUT="$(pwd)/helm/k8s-lite/values.registry.generated.yaml"

  # Create TLS secret if missing
  if ! kubectl get secret "$REG_TLS_SECRET" -n "$NAMESPACE" >/dev/null 2>&1; then
    echo "Creating self-signed TLS certificate for registry (secret: $REG_TLS_SECRET)"
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -subj "/CN=localhost" -keyout /tmp/registry-tls.key -out /tmp/registry-tls.crt >/dev/null 2>&1 || true
    kubectl create secret tls "$REG_TLS_SECRET" --cert=/tmp/registry-tls.crt --key=/tmp/registry-tls.key -n "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1 || true
    rm -f /tmp/registry-tls.key /tmp/registry-tls.crt
  else
    echo "TLS secret $REG_TLS_SECRET already exists; skipping cert generation."
  fi

  # Create htpasswd secret if missing (default admin:changeme)
  if ! kubectl get secret "$REG_HTPASS_SECRET" -n "$NAMESPACE" >/dev/null 2>&1; then
    echo "Creating htpasswd secret for registry (secret: $REG_HTPASS_SECRET)"
    # Use openssl APR1 hash to create htpasswd entry without requiring apache2-utils
    HTPASS_HASH=$(openssl passwd -apr1 "changeme")
    echo "admin:$HTPASS_HASH" >/tmp/registry-htpasswd
    kubectl create secret generic "$REG_HTPASS_SECRET" --from-file=htpasswd=/tmp/registry-htpasswd -n "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1 || true
    rm -f /tmp/registry-htpasswd
  else
    echo "htpasswd secret $REG_HTPASS_SECRET already exists; skipping htpasswd creation."
  fi

  # Emit a small values file to enable registry in Helm
  cat > "$VALUES_OUT" <<EOF
registry:
  enabled: true
  storage:
    type: hostPath
    hostPath: /var/lib/minimalist/registry
  access:
    hostPortEnabled: true
    hostPort: 5000
  tls:
    enabled: true
    secretName: $REG_TLS_SECRET
  auth:
    enabled: true
    htpasswdSecret: $REG_HTPASS_SECRET
    defaultUser: admin
EOF

  echo "Wrote registry values to $VALUES_OUT"
}

# Create registry secrets and values by default (can be skipped by setting SKIP_REGISTRY_SETUP=1)
if [ "${SKIP_REGISTRY_SETUP:-0}" != "1" ]; then
  echo "Ensuring local registry TLS + auth secrets exist (admin/changeme)."
  create_registry_secrets
else
  echo "Skipping registry secret creation (SKIP_REGISTRY_SETUP=1)."
fi

# Rotate / change registry password flow (interactive, but supports env overrides)
function rotate_registry_password() {
  if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl not available; cannot rotate registry password.";
    return
  fi

  REG_HTPASS_SECRET=${REG_HTPASS_SECRET:-registry-htpasswd}
  VALUES_OUT="$(pwd)/helm/k8s-lite/values.registry.generated.yaml"

  # If env vars provided, run non-interactively
  if [ -n "${REG_DEFAULT_USER:-}" ] && [ -n "${REG_DEFAULT_PASS:-}" ]; then
    USERNAME="$REG_DEFAULT_USER"
    PASSWORD="$REG_DEFAULT_PASS"
  else
    read -p "Change registry admin username (default: admin): " USERNAME
    USERNAME=${USERNAME:-admin}
    echo -n "Enter new password for $USERNAME: "; read -s PASSWORD; echo
    echo -n "Confirm password: "; read -s PASSWORD2; echo
    if [ "$PASSWORD" != "$PASSWORD2" ]; then
      echo "Passwords do not match. Aborting password change."; return 1
    fi
  fi

  HTPASS_HASH=$(openssl passwd -apr1 "$PASSWORD")
  echo "$USERNAME:$HTPASS_HASH" >/tmp/registry-htpasswd
  kubectl create secret generic "$REG_HTPASS_SECRET" --from-file=htpasswd=/tmp/registry-htpasswd -n "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1 || true
  rm -f /tmp/registry-htpasswd
  echo "Updated htpasswd secret: $REG_HTPASS_SECRET"

  # Update generated values to include defaultUser for downstream docs/consumers
  if [ -f "$VALUES_OUT" ]; then
    python3 - <<PYCODE || true
import sys,yaml
f='''$(cat <<'YAML'
$(cat "$VALUES_OUT")
YAML
)'''
try:
    obj=yaml.safe_load(f)
    obj.setdefault('registry',{}).setdefault('auth',{})['defaultUser']='''$(echo "$USERNAME")'''
    open('''$VALUES_OUT''','w').write(yaml.safe_dump(obj))
except Exception as e:
    print('WARN: failed to update values file',e)
PYCODE
  fi
}

# Prompt to rotate password unless non-interactive override provided
if [ "${SKIP_REGISTRY_SETUP:-0}" != "1" ]; then
  if [ -n "${REG_DEFAULT_USER:-}" ] && [ -n "${REG_DEFAULT_PASS:-}" ]; then
    echo "Non-interactive registry credentials provided via env; rotating password now."
    rotate_registry_password || true
  else
    read -p "Would you like to change the default registry admin password now? (y/N): " CHANGE_REG_PASS
    case "$CHANGE_REG_PASS" in
      [Yy]* ) rotate_registry_password || true;;
      * ) echo "Keeping default registry password (admin/changeme).";;
    esac
  fi
fi

# -------------------------
# Step 5: Intelligence & Major Selection (Operator Inputs)
# - Interactive prompts for external API keys and optional git pulls
# - Detects airgapped/network-less environments and disables external fetches
# -------------------------

# quick network check (used to decide whether pulling external repos / APIs is possible)
NETWORK_OK=false
if command -v curl >/dev/null 2>&1; then
  if curl -s --head https://www.google.com >/dev/null 2>&1; then
    NETWORK_OK=true
  fi
fi
if [ "$NETWORK_OK" = false ]; then
  echo "WARNING: Network appears unavailable (airgapped). External pulls and API integrations will be skipped unless provided locally."
fi

# OpenRouter / experiment API Key (positional arg supported for backward compatibility)
if [ -z "${1:-}" ]; then
  read -p "Enter OpenRouter / experiment API Key (optional): " API_KEY
else
  API_KEY=$1
fi

# WhatsApp / Nanobot integration
read -p "Enter WhatsApp / Nanobot API key (leave blank to skip): " WHATSAPP_API_KEY
if [ -n "$WHATSAPP_API_KEY" ] && [ "$NETWORK_OK" = false ]; then
  echo "Note: WhatsApp integration provided but network is unavailable; runtime connectivity will be required for outbound messaging."
fi

# GitHub API token (used by some operator flows)
read -p "Enter GitHub API token (leave blank to skip): " GITHUB_API_KEY

echo "Select your Lab Focus: (nlp / vision / sre)"
read -p "Focus: " MAJOR
MAJOR=${MAJOR:-nlp}

# Optional: Autoresearch repo pull (interactive)
read -p "Autoresearch repo URL to clone/pull (leave blank to skip): " AUTORESEARCH_REPO
if [ -n "$AUTORESEARCH_REPO" ]; then
  if [ "$NETWORK_OK" = true ]; then
    DEST_DIR="$(pwd)/opencode/third_party/autoresearch"
    mkdir -p "$(dirname "$DEST_DIR")"
    if [ -d "$DEST_DIR/.git" ]; then
      echo "Updating existing autoresearch at $DEST_DIR"
      git -C "$DEST_DIR" pull || echo "git pull failed; please inspect network or credentials"
    else
      echo "Cloning autoresearch into $DEST_DIR"
      git clone "$AUTORESEARCH_REPO" "$DEST_DIR" || echo "git clone failed; please inspect network or credentials"
    fi
    AUTORESEARCH_ENABLED=true
  else
    echo "Skipping autoresearch clone: network unavailable (airgapped). You can populate $DEST_DIR manually."
    AUTORESEARCH_ENABLED=false
  fi
else
  AUTORESEARCH_ENABLED=false
fi

# Optional: enable Nanobot runtime wiring
read -p "Enable Nanobot-WhatsApp integration in Helm (y/N)? " NANOBOT_YN
case "$NANOBOT_YN" in
  [Yy]* ) NANOBOT_ENABLED=true;;
  * ) NANOBOT_ENABLED=false;;
esac

# -------------------------
# Final: Summary + Helm command hint (operator will run helm install)
# This section builds a helpful `helm` command and will automatically inject
# the `helm/k8s-lite/values.generated.yaml` file (if present) via `-f`.
# -------------------------
echo "------------------------------------------"
echo "${BOLD}PRE-FLIGHT COMPLETE.${NORMAL}"
GENERATED_VALUES="$(pwd)/helm/k8s-lite/values.generated.yaml"

# Build base Helm command (user should replace the placeholder secret)
HELM_CMD=("helm" "install" "$HELM_RELEASE" "./helm/k8s-lite" "-n" "$NAMESPACE" "--create-namespace")
HELM_CMD+=("--set" "global.gpuEnabled=$GPU_FLAG")
HELM_CMD+=("--set" "global.major=$MAJOR")
if [ -n "${API_KEY-}" ]; then
  HELM_CMD+=("--set" "secret.openrouterKey=$API_KEY")
else
  HELM_CMD+=("--set" "secret.openrouterKey=<YOUR_API_KEY_HERE>")
fi

# Inject WhatsApp / Nanobot key into Helm values (or placeholder)
if [ -n "${WHATSAPP_API_KEY-}" ]; then
  HELM_CMD+=("--set" "secret.whatsappKey=$WHATSAPP_API_KEY")
elif [ "$NANOBOT_ENABLED" = true ]; then
  HELM_CMD+=("--set" "secret.whatsappKey=<YOUR_WHATSAPP_KEY_HERE>")
fi

# Inject GitHub token if provided
if [ -n "${GITHUB_API_KEY-}" ]; then
  HELM_CMD+=("--set" "secret.githubToken=$GITHUB_API_KEY")
fi

# Nanobot enable flag
if [ "$NANOBOT_ENABLED" = true ]; then
  HELM_CMD+=("--set" "integrations.nanobot.enabled=true")
else
  HELM_CMD+=("--set" "integrations.nanobot.enabled=false")
fi

# Autoresearch integration flags
if [ "${AUTORESEARCH_ENABLED:-false}" = true ]; then
  HELM_CMD+=("--set" "integrations.autoresearch.enabled=true")
  HELM_CMD+=("--set" "integrations.autoresearch.repo=${AUTORESEARCH_REPO}")
else
  HELM_CMD+=("--set" "integrations.autoresearch.enabled=false")
fi

if [ -f "$GENERATED_VALUES" ]; then
  HELM_CMD+=("-f" "$GENERATED_VALUES")
  echo "Detected generated values: $GENERATED_VALUES -> will be injected into Helm command"
fi

echo "Run the following command to launch the Lab:" 
echo ""
printf '%s ' "${HELM_CMD[@]}"
echo ""

if [ "$AUTO_DEPLOY" = true ]; then
  echo "Auto-deploy enabled — executing Helm command now..."
  "${HELM_CMD[@]}"
  echo "Helm install executed."
else
  echo "To auto-deploy, re-run with --yes or --auto-deploy."
fi

echo "Notes:"
echo " - Set VAULT_ADDR and VAULT_TOKEN in your environment to enable the Vault handshake."
echo " - Provide secret values to Helm using --set-file or Kubernetes Secrets; avoid committing literals into source control."
echo " - After Helm deploy, validate services, telemetry, and the scheduled validation CronJobs."
echo " - See helm/k8s-lite/VALUE_ADD.md for details on generated values and the bootstrap workflow."

exit 0
