# Lab Design — Machine-Readable & Human Overview

Files:

- `design.yml` — machine-readable manifest of components, prescan checks, tiers and enforcement rules.

Purpose:

This document summarizes the lab-level design decisions and points the agents to `design.yml` for programmatic configuration. Agents (n8n, ZeroClaw, Inspector) must consult `design.yml` before scheduling heavy work.

Key points:

- Prescan: every node or workstation runs the prescan checks described in `design.yml:prescan` and reports `lab_tier`.
- Tier mapping: choose `small`, `medium`, or `large` depending on hardware. The lab's agents enforce resource budgets according to the tier.
- Admission: training jobs must declare `dna_id`, `requested_vram_gb`, and `priority`; the Janitor enforces these.

Core model infra:

- `LM Studio` is treated as a core service for the lab: it provides the model development UI, experiment management, adapter application, and local model lifecycle. `LM Studio` should emit metrics and traces so Inspector and the Heatmap can evaluate local model performance.
- `Ollama` can be listed as an optional adapter for convenience and compatibility (many users expect it). However, Ollama does not expose low-level GPU telemetry to the cluster; therefore it must not be relied on for GPU power accounting or fine-grained VRAM scheduling. Prefer `LM Studio` or `LMDeploy` for production inference where telemetry and control are required.

Monitoring / Heatmap:

- The lab frontpage should include a Heatmap that visualizes running services (cells colored by service time or latency). The heatmap lives `front-and-center` on the Lungs dashboard.
- Hovering a cell shows quick metrics: service times (p50/p95), tokens used, inference times, RPS, and links to traces.
- A guarded `Kill -9` action is available on hover (or in the detail panel). The Kill action must require RBAC approval and an explicit confirmation dialog; Janitor will record the action and reason.

Why pgvector vs Mongo:

- I used Mongo as a quick placeholder in the initial n8n scaffold. For vector search, similarity, and AI workflows, `pgvector` (Postgres extension) is preferred:
	- Native SQL integrates with existing analytics and ACID guarantees.
	- `pgvector` has efficient vector indexing (ivfflat, hnsw) and better tooling for ML workflows.
	- Single source of truth (Postgres) simplifies backup, access control, and joins with metadata tables.
- Action: I changed the n8n workflow to write JSON rows into Postgres tables that can be used to build vectors and feed `pgvector` indexing.

Power cost monitoring:

- The dashboard will show a live power-cost tally for GPU usage priced at $0.10 per kWh. Data source: GPU power metrics (DCGM exporter or node exporter GPU metrics) scraped by Prometheus.
- Suggested Prometheus queries (examples):
	- Current total GPU watts: `sum(node_gpu_power_watts)`
	- Rolling energy (kWh) over last hour: `sum_over_time(node_gpu_power_watts[1h]) / 3600`
	- Cost per hour (USD): `(sum_over_time(node_gpu_power_watts[1h]) / 3600) * 0.10`
- UI: show current watts, 1h kWh, cost/hour, and accumulated cost since the lab build/start (use build/start timestamp emitted by agents). Place prominently on the Lungs frontpage alongside the heatmap.
- Implementation note: ensure your GPU exporter exposes power draw (DCGM exporter does). If not available, approximate by using GPU utilization × TDP for each GPU.

Remote hosting cost simulation:

- The dashboard will also show a simulated remote hosting cost card so you can compare local power spend vs using a remote endpoint.
- Presets are defined in `value-add/design.yml:remote_hosting:presets` (light/medium/heavy). Agents can run a quick estimate by supplying `requests_per_hour` and `avg_tokens_per_request`.
- Combined display: `local_power_cost + hourly_remote_cost` and `monthly_remote_cost`.
- API: add `/api/observability/remote-cost` to return estimates (see `value-add/remote-hosting-cost.md` for formulas and UI snippet).

Examples:

- Developer preset: `developer` uses `small` tier. Good for single 3090 experiments and AutoResearch runs overnight.
- Team preset: `team` uses `medium` — allows modest parallelism and more generous memory.

How agents should use this file:

1. Read `value-add/design.yml` at workflow start.
2. Run the prescan routine (GPU, driver, disk, cores, memory).
3. Map hardware to the nearest tier and set `lab_tier` label on the node or pod.
4. Enforce: reject or queue jobs that exceed the tier budgets; use Janitor to throttle lower-priority tasks.

Next steps (implementation):

1. Add a prescan utility script (shell/python) that writes node metadata to `k8s` labels and to the `pgvector` yard.
2. Add n8n nodes that call prescan before expensive workflows and perform `dry_run` budget estimations.
3. Update training job templates to require `dna_id` and resource annotations.

See `value-add/design.yml` for the detailed machine-readable configuration.
