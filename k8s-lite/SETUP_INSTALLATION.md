
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

## 9. Included Manifests / External Integrations (critical)

The lab can optionally integrate several external agent-building and orchestration projects. These are referenced here so operators know what external pieces may be pulled or configured during bootstrap/deploy.

- **Mastra (Agent Building Frameworks / React UI)**: https://github.com/mastra-ai/mastra — recommended as a dedicated React page / UI for agent building (Mastra Studio). We include this as a referenced integration; operators may host a Mastra frontend in the `react-dashboard` or as a separate service behind the Opencode gateway.
- **Pydantic AI**: https://github.com/pydantic/pydantic-ai — useful for schema/AI validation in agent workflows. Add as a Python dependency where agent services require strong typed inputs/outputs.
- **LangGraph**: https://github.com/langchain-ai/langgraph — graph-based orchestration primitives for agents; include connectors in `opencode` and `langchain`-enabled services.
- **Nanobot (WhatsApp connector)**: https://github.com/HKUDS/nanobot — target connector for WhatsApp. To enable it, operators must provide WhatsApp API credentials (see bootstrap notes below).
- **Autoresearch (lab sync)**: Autoresearch is typically pulled into the lab runtime (for example into `opencode/third_party/autoresearch` or `/opt/autoresearch`) via a `git pull` during bootstrap. By default we treat this as an optional network fetch; see the bootstrap script for an interactive option to clone/pull the repo.

Notes:
- These integrations require outbound network access. If your environment is airgapped, external pulling and live API integrations will not function — they must be provided as pre-baked images, local tarballs, or manually mirrored into the environment. The bootstrap will detect lack of network and warn the operator.
- We do not ship or vendor third-party code in this repository. Operators must agree to each project's license before pulling or running their code.

Airgap mirroring example:

If you operate in an airgapped environment, mirror repositories and packages from a networked machine, then transfer the artifacts into the airgapped lab. Example workflow:

1. On a networked host, mirror the repo and create tarballs:

```sh
# mirror git repository (bare mirror)
git clone --mirror https://github.com/your-org/autoresearch.git autoresearch.git.bundle
tar -czf autoresearch.git.bundle.tar.gz autoresearch.git.bundle

# optionally mirror other repos (mastra, langgraph, nanobot)
git clone --mirror https://github.com/mastra-ai/mastra mastra.git.bundle
tar -czf mastra.git.bundle.tar.gz mastra.git.bundle
```

2. Transfer artifacts into the airgapped environment (USB, secure transfer, or internal scp):

```sh
scp autoresearch.git.bundle.tar.gz user@airgapped-host:/opt/mirrors/
```

3. On the airgapped host, unpack and populate a local repo or filesystem path expected by the bootstrap:

```sh
cd /opt/mirrors
tar -xzf autoresearch.git.bundle.tar.gz
git clone autoresearch.git.bundle /opt/autoresearch
# or place into repo layout expected by bootstrap: opencode/third_party/autoresearch
mkdir -p /srv/minimalist/opencode/third_party
cp -r /opt/autoresearch /srv/minimalist/opencode/third_party/autoresearch
```

4. Adjust the bootstrap or Helm values to point at the local path (or set `integrations.autoresearch.enabled` to `false` and run local workloads manually).

Notes:
- For Python packages, create a local PyPI mirror (e.g., `bandersnatch` or `devpi`) and configure pip to use it.
- For container images, pull images in a networked environment, save them with `docker save`/`podman save`, transfer, and load with `docker load` on the airgapped host; optionally push them into an internal registry created above.
- Keep a documented list of mirrored artifact versions and checksums to ensure reproducibility and license compliance.

---

For operational guidance on enabling these integrations via the bootstrap, see `k8s-lite/bootstrap-nucleus.sh` which now prompts interactively for API keys, git-pull choices, and airgapped checks.
