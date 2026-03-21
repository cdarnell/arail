# Setup & Installation (Helm)

## Preferred Method

Use the Helm chart in `helm/k8s-lite` for all deployments. This is the single source of truth for the Minimalist stack.

### Install
```sh
helm install minimalist ./helm/k8s-lite
```

### Upgrade
```sh
helm upgrade minimalist ./helm/k8s-lite
```

## Pre-Install Auto-Discovery (Recommended)

Before installing the Helm chart, run the Pre-Install Probe to auto-discover host hardware and generate tuned `values.yaml` defaults. This step is recommended for first-time installs or when moving the lab to a new machine.

1. Ensure the probe dependencies are installed:

```bash
cd <repo-root>
python -m venv .venv
source .venv/bin/activate    # macOS / Linux
pip install -r scripts/preinstall/requirements.txt
```

2. Run the probe and generate recommendations:

```bash
python scripts/preinstall/hardware_probe.py --output helm/k8s-lite/values.generated.yaml
# Review helm/k8s-lite/values.generated.yaml and then apply if desired
python scripts/preinstall/hardware_probe.py --apply
```

3. Now install the Helm chart (with your verified values):

```bash
helm install minimalist ./helm/k8s-lite -f helm/k8s-lite/values.generated.yaml
```

Note: The repo includes `k8s-lite/preinstall-minimalist.sh` which will run the probe automatically if Python is available. The probe is conservative and intended as a helpful default—please review generated values before applying.

## Legacy/Manual

The `k8s-lite/` folder is deprecated and only for reference or manual/legacy use.

## Programmatic Setup with GitHub Actions

We provide a GitHub Actions workflow that automates validation and build steps to make the Lab setup reproducible, auditable, and operator-free. The workflow lives at `.github/workflows/ci-helm-vault-and-rust.yml` and performs these actions for each push/PR:

- Run chart dependency build and template validation (`scripts/ci/helm-validate.sh`).
- Build the Rust `agent_escalator` binary to catch compile-time regressions early.

Why use Actions for setup
- Reproducible: the same steps run in a clean runner, reducing "works on my machine" issues.
- Observable: CI logs show failures in templating, dependency resolution, or Rust builds.
- Gateable: require passing status checks before merging changes to `main`.
- Programmatic bootstrapping: Actions can, when authorized, run onboarding and provisioning scripts (for example, `scripts/ci/helm-validate.sh` and `k8s-lite/onboard-nucleus.sh`) against a test or production cluster.

Security & credentials
- Store short-lived credentials in repository or organization Secrets (e.g., `VAULT_ADDR`, `KUBECONFIG`, `VAULT_TOKEN`), or preferably use GitHub Actions OIDC to mint cloud credentials / Kubernetes service account tokens and avoid long-lived secrets.
- When CI must interact with a cluster, prefer a dedicated CI service account with the minimum RBAC privileges required for bootstrap (create roles, service accounts, and policies).
- Never commit secrets into the repo. The workflow we added assumes vault and kubectl credentials come from Actions Secrets or environment configured by your CI platform.

Recommended CI-driven setup flow (example)
1. `helm dependency build` for `helm/minimalist` (fetches dependencies).
2. `helm template` + validator script to ensure `app`/`version` labels and Vault-related templates render.
3. Build `agent_escalator` to ensure the agent compiles.
4. If tests pass and an operator approves, run onboarding automation that configures Vault auth, policies, and default roles. This step should run only in a controlled environment and use secure secrets or OIDC.

Note: The repository already contains a workflow that implements steps 1–3; extend it to perform step 4 only after you have reviewed and approved automation policies for your environment.
