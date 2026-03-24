# NuKaiZen Lab Architecture Overview

## Infrastructure Pivot
- Environment: Kubernetes Lite (k3s)
- Service Mesh: Linkerd (primary)
- All deployment manifests default to single-replica sets for single-node workstations
- Helm values allow scale-out compatibility

-## SRE Layer (ZeroClaw)
- ZeroClaw runs as a background daemon in its own namespace using the Linkerd mesh with per-pod `linkerd2-proxy` sidecars (Rust-based micro-proxy) — sidecar injection is used to provide mTLS and telemetry.
- Subscribed to Linkerd mesh tap data
- Monitors golden metrics (latency, error rate, throughput)
- If Linkerd reports >5% 5xx error rate for llm-gateway:
  - ZeroClaw initiates diagnostic loop
  - Checks local GPU health
  - Notifies opencode.ai (Teacher agent) if a workflow/class needs to be paused for repairs
- Auto-remediation: ZeroClaw triggers repair actions when circuit breakers trip or services fail

## Transient Workers & Shared-Memory mmap
- **Pattern:** For transient Python workloads, a memory-backed `emptyDir` ( `medium: Memory` ) stores pre-warmed model weights on the node. A dedicated loader populates this volume once at startup. Transient Pods mount the volume and use `mmap` to access weights with zero-copy semantics.
- **Advantages:** Avoids per-pod model loading I/O and memory duplication. Multiple concurrent transient pods can attach instantly to the same physical RAM, enabling sub-second start times.
- **Service Mesh:** Linkerd (sidecar-based) is used to provide mTLS and proxy-level observability via `linkerd2-proxy` sidecars so transient pods are secured and observable while keeping overhead low.
- **Orchestration & Validation:** Mastra acts as the dispatcher and uses Pydantic (pydantic-ai) to validate task schemas before creating transient Jobs/Pods, preventing resource waste on malformed requests.

## Local Image Registry
- **Purpose:** Provide a minimal, single-node image registry so the lab can host immutable images locally and seed the environment during bootstrap.
- **Design:** A small `registry:2` deployment uses a hostPath at `/var/lib/minimalist/registry` and exposes port 5000 on the host so local clients can push/pull to `localhost:5000`.
- **Seeding:** The repository includes `scripts/registry/refresh-registry.ps1` to mirror public images into the local registry. Use `docker` or a compatible tool to run the script.
- **Considerations:** This registry is intentionally minimal with no TLS/auth by default. For production or shared environments enable TLS and authentication, or run a hardened solution (Harbor, Quay).

## Persona Mapping
- **opencode.ai:** Teacher/Orchestrator (explains, guides, triggers workflows)
- **zeroclaw:** Janitor/SRE (monitors, repairs, optimizes infrastructure)

## Filesystem Structure
- `/kubernetes/base/linkerd/` — Mesh-specific policies
- `/kubernetes/apps/zeroclaw/` — SRE agent deployment

## Power-Aware Cost Simulator
- See VALUE_ADD.md for logic and workflow
- Default power cost: $0.10/kWh
- Compares local inference cost to cloud API pricing

---

This architecture enables a living AI ecosystem with self-healing, self-improving, and self-curating agents, optimized for workstation and scale-out environments.

## Unsloth + Autoresearch (High-level integration)

This section describes how to wire Unsloth (training/distillation engine) into the Autoresearch controller loop so the lab can perform continuous, policy-driven model improvement.

- Control / Brain (Autoresearch): a long-running Python Deployment that reads research goals (ConfigMap/CRD or `GOAL.yaml`), reads metrics and artifacts from Prometheus/MinIO/Postgres, and spawns parameterized K8s `Job` specs for Unsloth trainer runs. It records run metadata back to Postgres/pgvector and optionally to an experiment registry.

- Execution / Engine (Unsloth Trainer Jobs): short-lived `Job` / `CronJob` / Ray workers that run the Unsloth kernels to fine-tune or distill. Trainer jobs are parameterized via environment variables and annotations (see Downward API notes), mount PVCs for checkpoints and may push artifacts to MinIO (S3-compatible) object storage.

- Observability & UX (Studio / Nukaizen UI): Unsloth Studio deployed as a Deployment + Service for human interaction and the existing `react-dashboard` (Nukaizen / Nucleus UI) surface showing runs, loss curves, VRAM, and best models. Autoresearch writes run entries to a small `runs` table so Studio and the dashboard can overlay charts and drill into artifacts.

### Core Kubernetes primitives

- Autoresearch Controller: Deployment that watches goals and metrics, generates `batch/v1` `Job` manifests, and reconciles run outcomes.
- Trainer Jobs: CPU/GPU `Job` objects with resource requests/limits, PVC mounts for `/checkpoints`, and env vars such as `BASE_MODEL`, `STUDENT_MODEL`, `LR`, `MAX_STEPS`, `DATASET_PATH`.
- Storage: MinIO (S3) for datasets, checkpoints, and logs; optional PVCs for high-throughput local checkpointing.
- Metadata: Postgres + `pgvector` for run metadata, experiment registry, and vector search.

### Programmatic distillation loop (logical flow)

1. Define a research objective (human or policy-driven). Example: "Distill `mistral-7b` → 3B for domain Q&A with <X latency and >Y accuracy." 
2. Autoresearch selects candidate hyperparams, student size, distillation method and templates a K8s `Job` for Unsloth.
3. Trainer job runs for an enforced wall-clock or step budget, emits metrics (loss, eval, VRAM) and writes artifacts to object store.
4. Autoresearch evaluates metrics (Prometheus + JSON artifacts), updates `runs` registry and decides keep/retry/variation.

### Downward API (why it matters with Linkerd)

Linkerd provides networking, mTLS and proxy-level telemetry but does not expose Kubernetes pod identity and run-specific metadata to the application process. Use the Downward API to expose `POD_NAME`, `POD_NAMESPACE`, `NODE_NAME`, CPU/MEM requests & limits, and run-specific labels/annotations (e.g., `run-id`, `experiment`) into the trainer container. This ensures application logs, traces and metrics use the same tags as the proxy, enabling accurate correlation and graceful lifecycle coordination (early-stop annotations, run-level policies).

### Observability

- Prometheus: scrape trainer metrics either via a small `/metrics` endpoint or use a Pushgateway for very short-lived jobs. Scrape GPU metrics (DCGM), node exporter, and Linkerd proxy metrics.
- Grafana: dashboards for "Autoresearch Runs", "Trainer VRAM & Loss", and cluster GPU utilization. Use traces/spans (Tempo/OpenTelemetry) to correlate run steps if deep introspection is required.

### Unsloth Studio & Nukaizen UI

Run Unsloth Studio as an internal-facing Deployment with access to the same object store and Postgres registry. The `react-dashboard` ResearchPanel should read the `runs` table to overlay charts, allow dataset uploads (PDFs/recipes), and surface the lab's active work in real time.

### Inference engine choices (Ollama vs lmdeploy)

Ollama is provided in the repository as a convenient, developer-friendly local inference option and is purposefully "available" for quick experiments and single-user workflows. To reduce VRAM and storage footprint in the default inception deployment, Ollama is not pre-loaded with heavy models — operators can enable and seed Ollama from the local registry during setup when needed (see `SETUP.md`).

For production-grade, multi-tenant, high-throughput inference we recommend `lmdeploy` (the TurboMind engine). `lmdeploy` is specifically optimized for persistent/continuous batching, blocked/paged KV caching, and advanced VRAM management. These features make it a better fit than a standard Ollama deployment for Autoresearch workloads and multi-agent serving where throughput and shared VRAM efficiency matter.

Operational note: use Ollama for lightweight local testing and developer ergonomics; use `lmdeploy` for scaled, multi-tenant inference where batching and blocked KV caching materially improve performance and resource utilization.

## Documentation consolidation guidance

Current docs overlap in places (e.g., `About the Tech`, `ARCH_OVERVIEW.md`, `white-paper.md`, `BLUE_PRINT.md`, `autoresearch-GOALS.md`). Recommended canonical set:

- `README.md` — project elevator pitch and install/start instructions (keep minimal).
- `white-paper.md` — high-level vision, goals, and value propositions (audience: stakeholders).
- `BLUE_PRINT.md` — deployment pattern and product decisions (audience: operators/architects).
- `ARCH_OVERVIEW.md` — technical architecture and integration points (audience: implementers). Add the Autoresearch + Unsloth content here (done).
- `value-add/RUNBOOK.md` — operational recipes, detailed Job templates, SQL DDL, monitoring runbooks and run-level procedures.
- `GOAL.yaml` / `autoresearch-GOALS.md` — canonical place for machine-readable goals (keep `GOAL.yaml`) and store policy-level guidance in `autoresearch-GOALS.md` (or move into `value-add/` as a policy catalog).

Migration suggestion:

1. Move tactical, runnable artifacts (YAML templates, SQL) into `value-add/RUNBOOK.md` or `value-add/runbook/` folder and reference them from `ARCH_OVERVIEW.md`.
2. Replace verbatim copies in `About the Tech` and `ARCH_OVERVIEW.md` with a single canonical section (this file) and add brief redirects in the other docs.
3. Archive deprecated docs into `docs/archive/` with a short README explaining the consolidation mapping.

---

These additions focus the architecture narrative in `ARCH_OVERVIEW.md` while keeping operational detail and runnable artifacts in the Runbook. If you want, I can now:

- A) Commit this change (done) and create `value-add/runbook/` and move templates there, or
- B) Keep moving content step-by-step (create PR draft listing files to change).

Which next step do you want? 

## Performance Considerations

This section covers key runtime patterns and operational knobs for maximizing throughput and efficiency in a multi-agent lab (LMs/SLMs, lmdeploy, Ollama, etc.). Put tuning-level runbooks and exact configs in `value-add/runbook/observability.md` and `value-add/runbook/` templates.
### Serverless Grid (WASM gatekeepers + Ephemeral Python + Linkerd)

From a Performance Load Engineering perspective, the Serverless Grid pattern is essential when you want to run many agentic flows on prosumer hardware. It minimizes Resource Fragmentation and the Idle Tax by combining tiny, always-ready WASM gatekeepers with Just-In-Time ephemeral Python runtimes for heavy lifting. Key points:

- Eliminating the "Idle Tax" with WASM density: WASM modules have near-zero idle footprint and cold-start in microseconds–low milliseconds. You can safely run dozens of WASM gatekeepers that perform cheap validation and routing while keeping RAM available for the real resources (KV cache and model weights).

- Python as a "Transient Heavy-Lifter": The WASM layer performs lightweight schema validation (Pydantic-style) and only invokes Python when complex reasoning or library support (Unsloth, PyTorch, tokenizers) is required. Treat Python as a variable cost: spawn, attach to shared model memory, run, then exit to reclaim memory immediately.

- Linkerd as traffic regulator and backpressure layer: Use Linkerd service-level concurrency limits, retries and observability to prevent thundering-herd startups. When capacity is exhausted Linkerd's proxy and ServiceProfile settings provide backpressure/queueing and measurable cold-start latency so you can tune pre-warm strategies.

- Zero-copy efficiency via shared-memory `mmap`: Keep the model weights "warm" on a memory-backed volume (`emptyDir medium: Memory`) and have ephemeral Python runtimes `mmap` the weights on attach. This avoids heavy disk I/O and makes the ephemeral startup cost nearly equivalent to a persistent process but with 0% idle cost and no long-running memory leak creep.

Performance math (ephemeral call latency):
$$
T_{total} = T_{wasm\_init} + T_{python\_startup} + T_{mmap\_attach} + T_{inference}
$$
Because $T_{mmap\_attach}$ is nearly instantaneous and $T_{wasm\_init}$ is very small, the Serverless Grid delivers low overall latency while preserving RAM for the following priorities:

- **Inference runtime** (transient Python process, activations, buffers)
- **KV Cache** (Key-Value attention cache, grows with context)
- **Model Weights** (parameter tensors mmapped or resident in VRAM)

Keep those three explicitly reserved in your node-level resource accounting and admission-control rules.

Operational guidance:
- Pre-warm popular models into the shared-memory `mmap` volume during node boot or via a ramp job to reduce cold-starts.
- Use Linkerd `ServiceProfile` + tuning (timeouts, concurrency limits) to apply backpressure at the mesh layer rather than relying on OS swap.
- Monitor cold-start metrics and `page_fault`/`page_hits` for blocked/paged KV caching to adjust admission thresholds.

For concrete Linkerd `ServiceProfile` / `HTTPRoute` examples and timeout/retry snippets, see `value-add/runbook/observability.md` (we add YAML runbooks there to avoid cluttering this overview).

### Continuous Batching

Continuous batching allows the inference engine (e.g., `lmdeploy`) to accept new agent requests while a GPU is already processing tokens for other requests. Individual requests that arrive within the batch window are merged into a single GPU pass.

Benefit: If 12 agents send requests at slightly different times, the engine merges them into a single GPU pass. The cost of loading model weights into VRAM is paid once per batch, not 12 times, significantly increasing throughput and lowering amortized per-request cost.

Operational knobs:
- `batch_window_ms`: how long the engine waits to aggregate requests before forcing the batch.
- `max_batch_size`: upper bound to limit latency spike for very large crowds.
- `prefer_latency_threshold`: for high-priority requests, bypass batching if TFtT (time-to-first-token) is critical.

### Redis: Semantic Guard & State Store

Redis plays three roles in the multi-agent lab:

- Semantic Caching: Before an agent calls an LLM/SLM, check Redis for a cached response using a vector search index (approximate nearest neighbor on embeddings). If a similar query exists, Redis returns a cached answer (0-token cost).
- State Management: Store per-agent thread state, short pointers (UUIDs/ThreadIDs), and aggregated session metadata in Redis. Instead of passing large context windows between agents, send a small identifier and let the model-side loader fetch only the required sliced context.
- Rate Limiting / Admission Control: Use Redis as a queueing/admission controller. When many agents arrive, Redis can queue/bucket them to keep Time-to-First-Token (TTFT) within acceptable thresholds.

Patterns:
- Use Redis TTLs for cache freshness and Leaky-Bucket or Token-Bucket algorithms for admission control.
- Combine semantic cache keys with a small signature of the query + model-version to avoid stale mismatches.

### Sharing the VRAM: The KV Cache Dilemma

When many concurrent agents generate tokens, the dominant per-agent VRAM cost is the Key-Value (KV) cache used during autoregressive generation. A rough VRAM model for KV memory across concurrent agents is:

$$
Memory_{KV} = 2 \times L \times H \times D \times P \times C \times N
$$

Where:
- $L$ = number of layers (e.g., 32)
- $H$ = number of KV heads
- $D$ = head dimension (typically 128)
- $P$ = precision in bytes (e.g., 2 for FP16)
- $C$ = context length (e.g., 8192)
- $N$ = number of concurrent agents

This multiplication shows why naive concurrency multiplies VRAM quickly.

Solution: Blocked / paged KV caching (used by `lmdeploy`) treats KV memory like virtual memory, paging blocks in and out of VRAM to prevent fragmentation and allow many concurrent contexts to co-exist without full per-agent duplication. This reduces the effective VRAM footprint compared to keeping each agent's full KV cache resident.

Operational recommendations:
- Tune `block_size` and `page_cache_size` for your GPU(s) to balance throughput and IO.
- Monitor `vram_allocated`, `vram_free`, and `page_hits` metrics to detect thrashing.
- Set conservative admission thresholds when `page_fault_rate` grows to avoid overloaded GPUs.

### Where to put tuning & recipes

High-level rationale and component diagrams belong in this file (`ARCH_OVERVIEW.md`). Put exact config snippets, Helm values, Prometheus alerts, and `lmdeploy` tuning recipes in `value-add/runbook/observability.md` and the runbook templates so operators can apply them safely.

