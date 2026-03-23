Vault + Kubernetes-auth (providerless) — Architecture & Setup

Overview

- Goal: Use HashiCorp Vault as the canonical secrets store without requiring an external OIDC provider.
- Pattern: deploy Vault (in-cluster or external), enable `auth/kubernetes`, and let Pods prove identity using their ServiceAccount JWT (exposed via the Downward API).
- Benefits: providerless, automated, no long-lived env secrets, reproducible via CI.

High-level flow

1. Pod is deployed with a ServiceAccount and Downward API volume/env exposing `POD_NAMESPACE`/`POD_NAME` and `labels`.
2. The agent reads the in-cluster ServiceAccount JWT (or uses the TokenReviewer flow) and requests a token from Vault's `auth/kubernetes` endpoint.
3. Vault validates the JWT via the Kubernetes Token Reviewer and issues a Vault client token scoped to policies bound to the derived role.
4. The agent uses that Vault token to read KV v2 secrets (or dynamic credentials) at runtime.

Key conventions used in this repo

- Role derivation: roles are derived from namespace + app label: `<namespace>-<app>-role` (fallback: `<namespace>-role`).
- Downward API mount: `agentEscalator.downwardAPI.mountPath` (default: `/etc/podinfo/labels`) — templates inject this for agents.
- No plaintext secrets in values.yaml; Vault is the canonical source.

Automated bootstrap (CI / GitHub Actions)

- The repository includes a CI workflow that can bootstrap/validate Vault (see `.github/workflows/ci-helm-vault-and-rust.yml`).
- Recommended self-contained flow (no external OIDC provider):
  1. CI (or operator) installs Vault into a KinD or cluster via Helm (CI uses a dev Vault for integration tests).
  2. CI enables `auth/kubernetes` and writes the Kubernetes auth config using a token-reviewer ServiceAccount.
  3. CI creates policies and `auth/kubernetes/role` entries that bind ServiceAccount names and namespaces to Vault policies.
  4. CI seeds a public KV path and test secrets to validate read paths.
  5. CI runs `agent_escalator` inside a test Pod to verify the end-to-end k8s-auth login and secret reads.

Security notes & recommendations

- Prefer Kubernetes-auth (providerless) for self-contained, automated setups.
- Avoid long-lived Vault tokens unless strictly required. If long-lived tokens are needed, gate that creation and store them in a secure secret manager with limited scope.
- For production, combine Vault with an auto-unseal mechanism (cloud KMS or operator) and RBAC to limit what CI can do.

Quick commands (operator)

- Enable Kubernetes auth (example):

  vault auth enable -path=kubernetes kubernetes

- Configure token reviewer and kubernetes host/ca:

  vault write auth/kubernetes/config \
    token_reviewer_jwt="$SA_TOKEN" \
    kubernetes_host="$K8S_HOST" \
    kubernetes_ca_cert="$K8S_CA"

- Create a policy and role (example):

  cat > public-read.hcl <<'EOF'
  path "kv/data/public" {
    capabilities = ["read", "list"]
  }
  EOF
  vault policy write public-read public-read.hcl

  vault write auth/kubernetes/role/default-role \
    bound_service_account_names="vault-auth" \
    bound_service_account_namespaces="kube-system" \
    policies=public-read \
    ttl=24h

Where to find the repo automation

- Validator + CI helpers: `scripts/ci/helm-validate.sh`, `scripts/validate-helm-vault.sh`.
- CI workflow: `.github/workflows/ci-helm-vault-and-rust.yml` (includes an integration job that runs a Vault dev server and exercises the Rust binary).
- Onboarding script: `k8s-lite/onboard-nucleus.sh` includes a Vault bootstrap helper invoked with `VAULT_ADDR` and `VAULT_TOKEN`.

If you want, I can:
- Add a sample `vault-policy` manifest and an example `kubectl` job that the CI can run to create roles/policies automatically (non-interactive).
- Extend CI to provision a KinD cluster and install Vault there for a fully isolated integration test of the in-cluster login flow.

*** End of document
