# Vault Integration — Transparent Secret Management

Goal: make HashiCorp Vault the canonical secrets store for the lab and integrate it transparently so users and agents never handle raw secrets directly.

Principles
- Secrets live in Vault (KV v2 or dynamic engines). Do not store long-lived secrets in Kubernetes Secrets unless encrypted via CSI.
- Use Kubernetes Auth + CSI or Vault Agent Injector so workloads receive secrets as files or env vars without embedding tokens in code.
- Default to `--safe-mode` behavior for automated remediation. Human approval required for destructive actions.

Deployment (recommended)
1. Install Vault with the official Helm chart in namespace `vault`.
   - Use Raft storage for in-cluster HA.
   - Configure auto-unseal (cloud KMS or transit) for resilience.
2. Enable Kubernetes auth and create per-service policies/roles.

Quick Helm values (example)
```yaml
server:
  ha:
    enabled: true
  dataStorage:
    enabled: true
  telemetry:
    enabled: true
ui:
  enabled: true
injector:
  enabled: true
```

Auth & Policies (examples)
- Enable Kubernetes auth:
  - `vault auth enable kubernetes`
  - Configure with cluster CA and token reviewer.
- Example policy `opencode-policy.hcl`:
  ```hcl
  path "kv/data/opencode/*" {
    capabilities = ["read"]
  }
  path "database/creds/opencode-role" {
    capabilities = ["read"]
  }
  ```

Dynamic DB creds
- Use the Database secrets engine to issue short-lived DB credentials for Postgres/MySQL. Rotate and revoke via leases.

Injection patterns
- CSI Secrets Store (recommended): mounts secrets into Pods via `SecretProviderClass` without creating Kubernetes Secrets.
- Vault Agent Sidecar / Injector: runs a lightweight agent that fetches secrets and writes them to a shared volume.

Example SecretProviderClass (CSI)
```yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: vault-kv-opencode
spec:
  provider: vault
  parameters:
    vaultAddress: "https://vault.vault.svc.cluster.local:8200"
    roleName: "opencode-role"
    objects: |
      - objectName: "db-creds"
        secretPath: "kv/data/opencode/db"
        secretKey: "password"
```

Agent & App integration
- Agents (opencode, zeroclaw, agent_escalator) should prefer reading secrets from mounted files (CSI) or environment variables injected by Vault Agent.
- For CLI tools, use a service account with Kubernetes auth to request a Vault token at startup and fetch required secrets; prefer lease renewal and re-fetch on expiry.

User UX for tokens
- When a user must provide an external token (e.g., for a web crawler), n8n or the UI should accept the token via a secure form, mask it with `****` immediately, and write it to Vault at a controlled path (e.g., `kv/data/opencode/user-tokens/<id>`).
- The UI displays only obfuscated placeholders and allows revocation or rotation via the Vault API.

Audit & Hardening
- Enable audit devices (file or remote) in Vault for all access.
- Enforce short TTLs for dynamic credentials and rotate root credentials using operator procedures.
- Back up Raft data and secure auto-unseal credentials (KMS keys) separately.

Recommended next steps
- Add `helm/vault/values.yaml` to the repo with tuned defaults (I can add this file).
- Create example policies and `SecretProviderClass` manifests under `value-add/` (I can add these).
- Optionally, add Vault client support to `agent_escalator` to fetch secrets directly when CSI is not used.

Integration
- This lab requires Vault integration to be baked into the application stack and Kubernetes manifests. The platform will:
  - Automatically provision Vault (Helm) and configure Kubernetes auth via bootstrap scripts.
  - Create ServiceAccounts and Vault roles for agents (opencode, zeroclaw, agent_escalator) and bind least-privilege policies.
  - Inject pod metadata using the Downward API so agents can discover `POD_NAME`, `POD_NAMESPACE`, and labels (e.g., `app`) for role derivation and provenance.
  - Mount secrets via CSI or Vault Agent injector; the application code should read secrets from mounted files or env vars and never log raw values.

- Vault is used strictly for secrets (KV v2, dynamic DB creds, token storage). Certificate management and mesh mTLS (Linkerd) are handled separately and do not require Vault-managed passphrases in this setup.

- The Helm chart now includes templates to enable the Downward API for agent pods (`helm/minimalist/templates/deployment.yaml` and `helm/minimalist/templates/auto-research-job.yaml`), controlled by `agentEscalator.downwardAPI.enabled` in `values.yaml`.

Operational note: all of the above is automated via the provisioning scripts in `provisioning/vault/` so the user does not need to run manual Vault CLI steps except for operator-level configuration (auto-unseal keys, KMS setup).

Security note: Do not run Vault in `dev` mode for anything beyond local testing. Always use TLS and auto-unseal for production-like setups.
