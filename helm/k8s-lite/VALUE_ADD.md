**How the "Value Add" Works**

Overview
- By using a small set of conventions (a `global` values block, the Kubernetes Downward API, and W3C tracing), the Nucleus lab becomes "self-aware": components receive the context they need automatically and behave appropriately for the host they're deployed on.

Correlation
- The `global.major` value is injected into runtime environments for key services (for example, the `opencodeGateway` process receives `GLOBAL_MAJOR` in its env). Agents and adapters can read this value and adapt behavior (e.g., act as the "NLP Instructor") without manual prompts.

Observability
- `linkerd.enabled: true` is the default for the lab. When Linkerd is present, every enabled component (ollama, n8n, lmdeploy, grafana, etc.) is automatically added to the service graph and traces are correlated via W3C trace context. This provides end-to-end request flows in Tempo and visibility in Grafana.

Security
- `zeroclaw` (the Janitor) reads the Downward API-mounted pod metadata at `/etc/podinfo/labels` to determine release, role, and ownership. Based on the observed labels it requests a Vault role binding (for example, `zeroclaw-role`) via the Vault Kubernetes auth backend and enforces least privilege behavior.

Why this is high-quality
- Separation of Concerns: Users do not edit the complex `values.yaml` directly. Instead, `bootstrap-nucleus.sh` performs discovery and writes a `values.generated.yaml` containing only the minimal diffs required.
- Resource Safety: The bootstrap generation prevents attempting to run resource-heavy services on small hosts (for example, disabling Loki/Tempo on low-RAM machines).
- Native Feel: The bootstrap script and generated values create a direct, auditable transition from host-native discovery to a Helm-driven lab deployment.

How `bootstrap-nucleus.sh` assembles configuration
1. Hardware/host discovery (RAM, GPU count, CPU) is performed locally.
2. `values.generated.yaml` is created with only the overrides required (for example, enable GPU limits for `lmdeploy` when GPUs are detected, or disable heavy observability components on small hosts).
3. The operator runs the Helm command combining `values.yaml` and `values.generated.yaml` (the bootstrap script can auto-run `helm install` with `--auto-deploy`).

Operational notes
- Secrets: Do not write secrets into repo YAML. Provide secret values via `--set-file` or Kubernetes Secrets, or store them in Vault and let the opencode gateway read them.
- Extensibility: Add new test-case CronJobs or component toggles by editing the `components` section in `values.generated.yaml` (the bootstrap script can be extended to add more sizing rules).

Files of interest
- `helm/k8s-lite/values.yaml` — canonical defaults (overridden programmatically)
- `helm/k8s-lite/values.generated.yaml` — generated diffs from host discovery (created by `bootstrap-nucleus.sh`)
- `k8s-lite/bootstrap-nucleus.sh` — the discovery + generator + helper to run Helm

Backwards compatibility
- Templates that previously expected per-component `downwardAPI` configuration now read the shared `agentEscalator.downwardAPI` block; most components only need `components.<name>.enabled` and per-component overrides.

Summary
- The Value Add turns the lab from a static set of charts into an adaptive system that sizes and secures itself, reduces operator error, and boots with a clear separation between baseline defaults and environment-specific overrides.
