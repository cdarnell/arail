# Terraform Module: k3s-single-node

This module provisions a single-node k3s Kubernetes cluster (with optional GPU support) for Nucleus Lab.

## Usage

- Run `terraform init && terraform apply` in this directory.
- Set `gpu_enabled = true` to install NVIDIA GPU support (future extension).

## Outputs
- `kubeconfig`: Path to the generated kubeconfig file.
