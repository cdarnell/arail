#!/bin/bash
# Minimalist AI Lab: Pre-Installation Script for Ubuntu/WSL
# This script prepares your system for K3s, Helm, and kubectl usage.
# Usage: sudo ./preinstall-minimalist.sh

set -e

# 1. Update package lists and install dependencies
echo "Updating package lists and installing dependencies..."
apt-get update -y
apt-get install -y curl sudo systemd lsb-release \
  libmagic-dev poppler-utils tesseract-ocr libreoffice

echo "\n[AI Document Parsing] Installing Unstructured system dependencies: libmagic-dev, poppler-utils, tesseract-ocr, libreoffice..."
echo "If you do not need all document types, you may remove unneeded packages."

# 2. Install K3s (if not already installed)
if ! systemctl status k3s >/dev/null 2>&1; then
  echo "Installing K3s..."
  curl -sfL https://get.k3s.io | sh -s - --disable traefik
else
  echo "K3s is already installed and managed by systemd."
fi

# 3. Ensure kubectl is available and symlinked
K3S_KUBECTL="/usr/local/bin/kubectl"
if [ ! -f "$K3S_KUBECTL" ]; then
  echo "kubectl not found in /usr/local/bin. Creating symlink to K3s kubectl..."
  ln -s /var/lib/rancher/k3s/data/$(ls /var/lib/rancher/k3s/data/ | head -n1)/bin/kubectl /usr/local/bin/kubectl
else
  echo "kubectl symlink already exists."
fi

# 4. Install Helm (if not already installed)
if ! command -v helm >/dev/null 2>&1; then
  echo "Installing Helm..."
  curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
else
  echo "Helm is already installed."
fi

# 5. Validate cluster and tools
echo "Validating K3s cluster and tools..."
kubectl get nodes
helm version

# 6. Auto-Discovery: run hardware probe to generate tuned `values.yaml` recommendations
PROBE_PY="$(pwd)/scripts/preinstall/hardware_probe.py"
if [ -f "$PROBE_PY" ]; then
  echo "Running Pre-Install Hardware Probe (auto-discovery)..."
  # Prefer a virtualenv if available, otherwise use system python
  if command -v python3 >/dev/null 2>&1; then
    python3 "$PROBE_PY" --output "$(pwd)/helm/k8s-lite/values.generated.yaml" || echo "Probe ran but returned non-zero status. Check script output."
  elif command -v python >/dev/null 2>&1; then
    python "$PROBE_PY" --output "$(pwd)/helm/k8s-lite/values.generated.yaml" || echo "Probe ran but returned non-zero status. Check script output."
  else
    echo "Python not found. Skipping hardware probe. Install Python3 and run scripts/preinstall/hardware_probe.py manually." >&2
  fi
  echo "Hardware probe complete. Generated: helm/k8s-lite/values.generated.yaml"
  echo "Review the generated file before applying. To apply: python scripts/preinstall/hardware_probe.py --apply"
else
  echo "Hardware probe not found at scripts/preinstall/hardware_probe.py — skipping auto-discovery."
fi

# 6. Success message
echo "Pre-installation complete. K3s, kubectl, and Helm are ready."
