#!/bin/bash
# Minimalist AI Lab: Pre-Installation Script for Ubuntu/WSL
# This script prepares your system for K3s, Helm, and kubectl usage.
# Usage: sudo ./preinstall-minimalist.sh

set -e

# 1. Update package lists and install dependencies
echo "Updating package lists and installing dependencies..."
apt-get update -y
apt-get install -y curl sudo systemd lsb-release

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

# 6. Success message
echo "Pre-installation complete. K3s, kubectl, and Helm are ready."
