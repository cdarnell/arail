

# PROJECT NUCLEUS: The Living AI Blueprint

> **A self-evolving, fully observable AI ecosystem for the technologist wanting to truly understand AI.**

Project Nucleus is a **mesh-driven, fully observable AI laboratory** designed to remove the "integration bother" from the learning process while offering a full enterprise-grade experience. It treats your infrastructure as a living research subject, using **Autonomous Research, Chaos Engineering, and SRE Agents** to make the Nucleus smarter every single day.

Define your goal and let the system iterate toward it automatically. Nucleus's overarching objective is continuous self-refinement — faster, leaner, and more efficient with each cycle.

---

## 🧬 The Core Philosophy: Autonomous Evolution

The heart of Project Nucleus is the **Autoresearcher**, an evolutionary engine inspired by Karpathy-style experimentation that treats idle compute cycles as "nutrients" for system refinement. As long as your goal can be measured, the system will pursue it autonomously.

- **Self-Improving by Default:** When idle, the Nucleus analyzes referenced models to remove redundant multilingual weights and fine-tunes specialized Small Language Models (SLMs) for assigned roles (e.g., Janitor, Teacher).
- **Zero Subscription Anxiety:** Project Nucleus is designed to operate with **no required subscriptions** by default — you own your intelligence.
- **Eliminating Token Anxiety:** Integrated **Spend Simulation** models token usage, throughput, and cost-equivalency so you can validate trade-offs locally before using cloud resources.
- **Intuitive RAG Memory:** Nucleus correlates open notebooks and research with a pluggable RAG-style memory so each inference builds on the previous context.
- **Resource Prioritization:** The system aggressively optimizes VRAM and CPU allocation for core AI tasks, ensuring intelligent workloads get priority.

### Architectural Pillars

- **Event-Driven Backbone (Kafka):** The central nervous system for system signals, agent comms, and telemetry — enabling asynchronous, decoupled AI workflows.
- **Agentic Framework (PydanticAI & Mastra):** Type-safe, structured reasoning with robust orchestration and agent visibility.
- **Total Observability:** Built on Linkerd service mesh for live maps, metrics, and traceability of event flows.
- **Strategic Chaos:** A Chaos Monkey introduces controlled faults (latency, service drops, message bus interruptions) to surface self-healing and resiliency improvements.
- **Air-Gapped & Secure:** Privacy-first by default; the blueprint operates locally with optional, granular cloud integrations.

## 🚀 Quickstart

1. **Clone the Blueprint:**

	`git clone https://github.com/cdarnell/minimalist-blueprint.git`

2. **Trigger the Bootstrap:**

	`./bootstrap-nucleus.sh`

	*(This will prompt you for your primary Goal and environment options. If remote access such as premium model connectivity, please provide API details)*

3. **Explore and Evolve:**

	Explore the Agentic and Telemetry dashboards to watch the Autoresearcher, Spend Simulator, and ZeroClaw SRE in action.

	Control how aggressive the Nucleus is by selecting a mode during `./bootstrap-nucleus.sh` or via environment variables:

	- **Minimalist:** set `NUCLEUS_MODE=minimalist` — minimal background work: background autoresearch reduced, strategic chaos disabled, and only essential manifests come online (core services, Open Notebook, lightweight model runtimes). Ideal for local or low-resource setups.
	- **Balanced (default):** set `NUCLEUS_MODE=balanced` — the system selects recommended manifests based on available resources and user preferences (for example, enabling Open Notebook but not Jupyter by default). Balanced acts as a manifest-picker to provide a sensible middle ground.
	- **Extremist:** set `NUCLEUS_MODE=extremist` — aggressive autotuning, Chaos Monkey experiments, full SLM fine-tuning, and all optional manifests (JupyterLab, advanced telemetry, experimental agents) are enabled.

	You can toggle features or pick exact manifests via configuration under `core/defaults/`, `k8s-lite/`, or by using env vars. Examples:

	- `NUCLEUS_MODE=minimalist|balanced|extremist`
	- `NUCLEUS_CHAOS=true|false`
	- `NUCLEUS_SPEND_SIM=true|false`
	- `NUCLEUS_OBSERVABILITY=linkerd|none`
	- `NUCLEUS_MANIFESTS=open-notebook,grafana` (explicitly bring only these manifests online)

	For example, to avoid bringing up Jupyter but keep Open Notebook, use `NUCLEUS_MANIFESTS=open-notebook,grafana` or set `ENABLE_JUPYTER=false` in your local config so the Balanced mode will omit Jupyter manifests.

---

*Project Nucleus: Because your AI lab should be as smart as the models running inside it.*

