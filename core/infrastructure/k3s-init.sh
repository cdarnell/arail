#!/bin/bash
# K3s initialization script with resource-aware sizing
MEM_GB=$(awk '/MemTotal/ {printf "%.0f", $2/1024/1024}' /proc/meminfo)
if [ "$MEM_GB" -lt 8 ]; then
  echo "[INFO] Detected <8GB RAM. Installing K3s with minimalist profile."
  curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik --disable metrics-server" sh -
else
  echo "[INFO] Detected >=8GB RAM. Installing K3s with full profile."
  curl -sfL https://get.k3s.io | sh -
fi
