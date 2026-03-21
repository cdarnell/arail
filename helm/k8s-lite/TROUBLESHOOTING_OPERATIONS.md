# Troubleshooting & Operations

- All manifests are now managed via Helm in `helm/k8s-lite`.
- For manual troubleshooting, you may reference the old `k8s-lite/` folder, but all changes should be made in Helm templates.
- Use `helm status minimalist` and `kubectl get pods` for health checks.
