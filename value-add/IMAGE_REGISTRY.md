# Image Registry: How-To (Local, Secure, Scriptable)

This document describes how the Minimalist lab hosts a tiny, local image registry for single-node development (Linux/macOS/WSL). It uses a minimal Docker Registry (`registry:2`) exposed on `localhost:5000` and supports TLS + basic auth for secure local pushes. The bootstrap script automates secret generation and Helm wiring so the registry is ready before charts deploy.

Goals
- Self-host images locally with low complexity
- Secure with TLS + basic auth (no external CA required)
- Scriptable: prefer `regctl` for mirroring, fallback to Docker when required
- Cross-platform tooling: run from Ubuntu/WSL/macOS using the provided shell script

Quick features
- Registry: `localhost:5000` (hostPort for single-node)
- Default admin credentials: `admin` / `changeme` (change after first use)
- Mirrors: use `regctl image copy` (recommended) or `docker pull/tag/push` fallback

Bootstrap automation (what the script does)
1. Creates a self-signed TLS certificate for `localhost` and stores it as Kubernetes TLS secret `registry-tls`.
2. Generates an `htpasswd`-style secret `registry-htpasswd` with default user `admin` and password `changeme`.
3. Writes `helm/k8s-lite/values.registry.generated.yaml` with the registry toggles (enabling TLS and auth) so Helm will mount the secrets into the registry.

How to run (manual quickstart)
1. Ensure Kubernetes is reachable (K3s in WSL/Ubuntu is recommended):
```bash
kubectl get nodes
```
2. Deploy the registry (Helm chart or raw manifest):
```bash
# if using the templated manifest in this repo
kubectl apply -f helm/k8s-lite/templates/registry/90-local-registry.yaml
```
3. Mirror an image with `regctl` (recommended):
```bash
# install regctl (single binary) then:
regctl image copy --insecure docker.io/library/busybox:latest localhost:5000/library/busybox:latest
```
If `regctl` is unavailable, use the repository scripts:
```bash
./scripts/registry/refresh-registry.sh images.txt
```

Notes about TLS and `--insecure`
- The bootstrap uses a self-signed cert for `localhost`. `regctl` can accept self-signed certs with `--insecure` during initial seeding. For production, replace with a CA-signed cert and set `registry.tls.enabled=true` in your secure values file.

Why `regctl`?
- Single static binary, focused on registry ops, fast and scriptable.

Configuration (values)
The bootstrap creates or updates `helm/k8s-lite/values.registry.generated.yaml` with the following keys:

```yaml
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
    secretName: registry-tls
  auth:
    enabled: true
    htpasswdSecret: registry-htpasswd
```

Security note
- Default credentials are intentionally weak (`admin`/`changeme`) to make bootstrap simple. Change the password immediately after first use by updating the `registry-htpasswd` secret and rotating images that depend on those credentials.

Advanced options
- In multi-node clusters replace `hostPath` with a PVC backed by local-path or network storage.
- For advanced mirroring or CI workflows, use `skopeo` or `crane` where their features are needed. For simple copy/seed operations `regctl` is preferred.

Troubleshooting
- If the registry doesn't accept pushes: verify the secret names and that the registry pod has the mounts (`kubectl describe pod ...`).
- If `regctl` fails with TLS, retry with `--insecure` or import the self-signed cert into your OS trust store.

Appendix: regctl example
```bash
# copy an image into the local registry (accepting self-signed certs)
regctl image copy --insecure ghcr.io/mastra/mastra-controlplane:latest localhost:5000/mastra/mastra-controlplane:latest
```
