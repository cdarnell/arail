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

Mastra AI + Pydantic: Agent Orchestration
- **Validation Layer:** The Mastra control plane (Bun runtime) uses Pydantic (pydantic-ai) to statically validate incoming orchestration requests (input schema, allowed libraries, resource constraints). Requests that fail validation are rejected before any pod cold-start occurs.
 - **Service Mesh:** Designed for Linkerd (sidecar-based) mode so transient worker pods receive mTLS and telemetry via a lightweight per-pod `linkerd2-proxy` sidecar.
- **Model Pre-warm / Shared Memory:** A single-node pre-warm Job writes model weights to a hostPath-backed directory (recommended ` /var/lib/minimalist/models` on Linux). Transient Python workers mount and mmap these weights for zero-copy execution.
- **Observability:** Mastra Studio captures logical traces (validation → handoff). Physical telemetry (eBPF, node RAM usage, network) flows into Grafana/Tempo via Linkerd and existing observability templates.

Chart templates added:
- `templates/ai/80-mastra-controlplane.yaml` — Mastra Deployment + Service
- `templates/ai/81-mastra-validation-configmap.yaml` — ConfigMap placeholder for Pydantic rules/schema
- `templates/ai/82-model-prewarm-job.yaml` — single-node model pre-warm Job (hostPath guidance)

Notes
- This approach targets a single-node Linux Kubernetes cluster and prioritizes minimal runtime overhead. For multi-node clusters, replace the hostPath pre-warm with a cluster-shared filesystem or PVC backed by tmpfs-capable storage.
- The pydantic-ai project (https://github.com/pydantic/pydantic-ai) is the reference for validation schema formats and can be integrated into the Mastra control plane to enable static analysis and rejection of invalid tasks.

Local Image Registry (zero-bloat mirroring)
- **Purpose:** Provide a tiny, single-node local registry to host immutable images for the lab and allow bootstrap mirroring of public images.
- **Design:** A `registry:2` Deployment is included which exposes port `5000` on the host via `hostPort: 5000` so that Docker/containers on the host can push/pull with `localhost:5000`.
- **Storage:** Uses a hostPath at `/var/lib/minimalist/registry` on the node. This keeps the registry state local; retention policies are not configured by default.
- **Seeding:** See `scripts/registry/refresh-registry.ps1` — a small PowerShell script that pulls public images, retags them as `localhost:5000/<owner>/<repo>:<tag>` and pushes them into the local registry.
- **Security:** For lab usage this registry is intentionally minimal and unsecured. For networked or multi-user environments enable TLS + basic auth, or front with an ingress and mTLS via Linkerd.

Files added:
- `templates/registry/90-local-registry.yaml` — lightweight registry Deployment + Service
- `scripts/registry/refresh-registry.ps1` — mirror script using Docker

Shared-Memory mmap Pattern (Transient Python Workers)
- **Pattern:** Pre-warm model weights into a memory-backed volume (`emptyDir.medium=Memory`) and let transient workers `mmap` the weights for zero-copy access.
- **Model Pre-warm:** The chart includes `templates/ai/82-model-prewarm-job.yaml` as an example Job that writes weights to a hostPath-backed folder on single-node clusters. For multi-node environments use a clustered shared volume.
- **Gold Image Recommendations:** Use a minimal, precompiled Python image (no runtime pip installs) with `.pyc` files and compiled C-extensions to keep start times <1s.

YAML snippet (worker Pod mounting shared memory-backed model-store):

```yaml
apiVersion: v1
kind: Pod
metadata:
	name: python-transient-worker
spec:
	containers:
	- name: worker
		image: gentoofoo/python-base:latest
		volumeMounts:
		- name: model-store
			mountPath: /models
		resources:
			limits:
				memory: "2Gi"
	volumes:
	- name: model-store
		emptyDir:
			medium: Memory

Gentoofoo API Standardization & Linkerd Clarification
----------------------------------------------------------

Core intent: enforce a Contract-First architecture where OpenAPI 3.1 is the source-of-truth
for routing, validation, and observability. Linkerd uses per-pod sidecars (`linkerd2-proxy`) to provide mTLS and telemetry; for L7/path-based routing and contract validation convert OpenAPI specs into HTTPRoute or other gateway resources the mesh can enforce. This is Linkerd-specific — do not confuse with Istio Ambient semantics.

Key points
- **OpenAPI 3.1 Required:** Every service must expose a valid OpenAPI 3.1 spec. Specs drive
	Pydantic model generation, TypeScript client generation, and Kubernetes Gateway API (HTTPRoute)
	manifests used by Waypoint proxies.
- **Payload & Errors:** Use strict JSON payloads and RFC 7807 (Problem Details) for errors so
	Mastra can parse and correlate issues programmatically (include a `gentoofoo_trace_id`).
- **Versioning:** Use URL-based semantic versioning (for example `/v1/`) to enable mesh-level
	traffic-splitting and Waypoint routing without code changes.
 - **Sidecar vs L7 Gateways:** Linkerd relies on per-pod sidecars (`linkerd2-proxy`) for data-plane behavior. For L7 routing/validation and path-level observability, you may use Kubernetes Gateway API (`HTTPRoute`) or an API gateway in front of services; avoid conflating Linkerd with Istio's Ambient/Waypoint model.

Conceptual Communication Flow (single-node ASCII)
=============================================================================================
KUBERNETES SINGLE-NODE CLUSTER (HOST RAM: 64GB)
=============================================================================================

	PERSISTENT WORKLOADS ]
		NAMESPACE: gentoofoo-control
    
			+------------------------+
			| POD: mastra-controller |    (A) REQUEST
			| (Bun Runtime)          |------------------+
			| Sidecar injected       | (per-pod `linkerd2-proxy`) |
			+------------------------+                  |
																								v
[ LINKERD MESH PLANE ]                          |
	(Per-pod `linkerd2-proxy` sidecars providing mTLS, telemetry, and routing) |
																								|
		+------------------------+                  | (B) INTERCEPT & IDENTIFY
		| Linkerd Sidecar (L4)   | <----------------+     Uses Downward API
		| (linkerd2-proxy per-pod)|                       for Pod Identity
		+------------------------+                  |
																								| (C) mTLS WRAP & ROUTE
																								|
																								v
		+------------------------+                  |
		| API Gateway / HTTPRoute| <----------------+ (D) OPENAPI-BASED ROUTING
		| (Applies HTTPRoute or  |                        Validates against Contract
		|  gateway rules)        |                  |
		| (L7 enforcement at gateway/ingress)       |
		|                                            |
		+------------------------+                  |
		+------------------------+                  |
																								|
[ TRANSIENT WORKLOADS ]                         | (E) mTLS UNWRAP
	NAMESPACE: gentoofoo-workers                  |
																								|
		+------------------------+                  v
		| POD: python-transient  |    (F) EXECUTE
		| (Job/Pod - sidecar injected)|<-----------------+
		+------------------------+
				|
				| (G) MMAP ATTACH (Zero-Copy)
				v
		+------------------------+
		| VOLUME: shm (Memory)   |
		| (Pre-loaded Models)    |
		+------------------------+

=============================================================================================

Add this section to other READMEs (observability, ARCH_OVERVIEW.md, AI Lab In a Box.md) as
needed to keep the architecture clear and avoid Linkerd/Ambient confusion.
```
