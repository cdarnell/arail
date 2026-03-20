
# Minimalist AI Lab: Setup & Installation Guide


## Pre-requisites: Automated Pre-Installation (Ubuntu/WSL)

To automate all pre-installation steps (system update, K3s, kubectl symlink, Helm), use the provided script:

```sh
sudo ./k8s-lite/preinstall-minimalist.sh
```

This script will:
- Update your system and install required dependencies
- Install K3s (if not already installed) and start it with systemd
- Ensure `kubectl` is available and symlinked to `/usr/local/bin/kubectl`
- Install Helm (if not already installed)
- Validate your cluster and toolchain

After running the script, you should see your node in the Ready state with `kubectl get nodes` and Helm version output with `helm version`.


## Local DNS Setup (/etc/hosts)
For local development, add the following entries to your `/etc/hosts` file to map internal service URLs:

```sh
# Gentoofoo internal services
127.0.0.1 lab.gentoofoo.local
127.0.0.1 opencode.gentoofoo.local
127.0.0.1 lmdeploy.gentoofoo.local
127.0.0.1 prometheus.gentoofoo.local
127.0.0.1 grafana.gentoofoo.local
127.0.0.1 n8n.gentoofoo.local
127.0.0.1 kafka.gentoofoo.local
127.0.0.1 jupyter.gentoofoo.local
```

## Prerequisites
- Ubuntu 22.04 LTS (recommended)
- K3s (single node, systemd-managed)
- kubectl (bundled with K3s), helm, and kustomize installed
- GitHub account and access to this repository
- (Optional) Linkerd CLI for mesh diagnostics

## 1. Clone the Repository
```sh
git clone https://github.com/your-org/minimalist.git
cd minimalist
```

## 2. Configure Your Environment
- Edit `k8s-lite/00-namespace.yaml` to set your namespace
- Edit manifests in `k8s-lite/` for storage class, resource limits, and domains
- (Optional) Configure secrets for your environment


## 3. Deploy the Stack (Manual)
Once K3s is running and kubectl is working, deploy all manifests:
```sh
kubectl apply -f k8s-lite/
```

## 4. Deploy via GitHub Actions (CI/CD)
- Add your cluster's KUBECONFIG as a GitHub secret named `KUBECONFIG`
- On push/PR to `main`, `.github/workflows/ci-cd.yml` will:
  - Render Helm charts (if present)
  - Apply all manifests in `k8s-lite/`
  - Validate pod and service status

## 5. Access the UIs
- Grafana: http://<grafana-domain>:3000
- Prometheus: http://<prometheus-domain>:9090
- Phoenix: http://<phoenix-domain>:6006
- n8n: http://<n8n-domain>:5678
- JupyterLab/Open Notebook: http://<notebook-domain>:8888

## 6. Import the Unified Grafana Dashboard
- In Grafana, import `observability/ai-lab-unified-dashboard.json`

## 7. Troubleshooting & Validation
- See `k8s-lite/TROUBLESHOOTING_OPERATIONS.md` for pod status, logs, mesh, and telemetry checks
- Use `linkerd check` and `kubectl get pods -A` to validate health

## 8. Push-Button Setup (Helm)
- (Planned) All manifests will be templated as a Helm chart in `helm/`
- To install via Helm (when available):
  ```sh
  helm install minimalist ./helm/
  ```

---

Keep this guide updated as the stack evolves. For advanced automation, extend the GitHub Actions workflow and Helm chart as needed.
