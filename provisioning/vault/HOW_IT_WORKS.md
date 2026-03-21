Vault: How it Works (Minimalist overview)
=======================================

Scope
-----
This document explains the minimal Vault integration used by Minimalist: how pods authenticate to Vault (Secret Zero), how roles and policies are created, how the Downward API helps derive Vault roles, and why the onboarding scripts take the steps they do.

Core concepts
-------------
- Secret Zero: an operator-provided `VAULT_TOKEN` used during bootstrap to configure Vault (enable auth backends, write policies/roles). This token is not used by workloads.
- Kubernetes auth (auth/kubernetes): Vault validates a pod's ServiceAccount JWT with the k8s API (via a token-reviewer SA) and returns a Vault token mapped to a Vault role.
- Vault role: binds Kubernetes service accounts/namespaces to Vault policies. Minimalist uses names like `<namespace>-<app>-role` or `<app>-role`.
- Downward API: injects pod metadata (name, namespace, labels) and/or mounts `/etc/podinfo/labels`. Agents use this to derive a least-privilege Vault role when one is not explicitly supplied.

Bootstrap flow (what `k8s-lite/onboard-nucleus.sh` does)
------------------------------------------------------
1. Create a token-reviewer ServiceAccount (`vault-auth`) in `kube-system` and bind `system:auth-delegator` so Vault can validate tokens.
2. Obtain a ServiceAccount token (preferred: `kubectl create token`). For K8s >=1.24 the script will create a `kubernetes.io/service-account-token` Secret and wait (up to 30s) for it to populate.
3. Read the cluster API server host and CA (for Vault to call the k8s API).
4. Enable the `auth/kubernetes` backend and write `auth/kubernetes/config` with `token_reviewer_jwt`, `kubernetes_host`, and optionally `kubernetes_ca_cert`.
5. Create a public KV path and a small `public-read` policy as an example.
6. Create a default Vault role bound to the `vault-auth` SA (e.g., `default-role`) so the bootstrap process can validate the configuration.

Why create a SA token secret explicitly?
---------------------------------------
Kubernetes v1.24+ does not auto-create long-lived secret tokens for ServiceAccounts. Bootstrapping Vault requires a token-reviewer JWT; creating the token Secret ensures the bootstrap works across distributions (k3s, kind, managed k8s).

How workloads (agents) authenticate at runtime
---------------------------------------------
1. Workloads (e.g., `agent_escalator`) are configured with `VAULT_ADDR` + either a token or instructions to use Kubernetes auth.
2. If no `VAULT_TOKEN` is present, the agent attempts to derive a Vault role:
   - CLI `--vault-k8s-role` (explicit)
   - Pod label `app` (preferred) → role `namespace-app-role` or `app-role`
   - Namespace fallback → `namespace-role` (less granular; agent now logs a warning)
3. Agent reads the in-cluster SA JWT (`/var/run/secrets/.../token`) and posts `{role, jwt}` to `${VAULT_ADDR}/v1/auth/kubernetes/login`.
4. If successful, Vault returns a client token that the agent uses to read KV secrets (KV v2) with least privilege.

Policy & role hygiene
----------------------
- Prefer creating a 1:1 mapping: ServiceAccount == app name; Vault role named `<namespace>-<app>-role` and policy scoped to required KV paths. The provisioning helper `create-vault-k8s-role.sh` now ensures ServiceAccounts exist.
- Avoid namespace-wide roles unless necessary. Agents emit warnings when falling back to namespace roles to make misconfigurations visible.

Values and toggles
------------------
- `agentEscalator.downwardAPI.enabled` (helm): toggles env + volume mount for pod metadata. Default mount path: `/etc/podinfo`.
- `vault.enabled` and `vault.auth_path` in chart values control whether Vault is assumed present and which `auth` path is used.

Troubleshooting checklist
-------------------------
- Vault bootstrap fails: ensure `VAULT_ADDR` and `VAULT_TOKEN` are set for operator, check the token-reviewer SA and that its JWT is readable.
- Agent fails to login: verify the derived role exists in Vault and is bound to the SA namespace/name; check that the SA JWT is readable in the pod and that `VAULT_ADDR` is reachable.
- Missing Downward API data: set `agentEscalator.downwardAPI.enabled: true` or rely on explicit `--vault-k8s-role`.

Files of interest
-----------------
- `k8s-lite/onboard-nucleus.sh` — bootstrapper: enables kubernetes auth, writes config and default role.
- `provisioning/vault/create-vault-k8s-role.sh` — helper to create a role and ensures ServiceAccounts exist.
- `sdk/src/bin/agent_escalator.rs` — runtime role derivation, Downward API parsing, and Vault login flow.

If you want, I can:
- Add an example policy for a common pattern (e.g., `path "kv/data/<app>/*" { capabilities = ["read"] }`).
- Add an audit/logging example (sending the namespace-fallback warnings to Prometheus/Grafana).
