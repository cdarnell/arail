# Nucleus Lab Architecture Overview

## Infrastructure Pivot
- Environment: Kubernetes Lite (k3s)
- Service Mesh: Linkerd (primary)
- All deployment manifests default to single-replica sets for single-node workstations
- Helm values allow scale-out compatibility

## SRE Layer (ZeroClaw)
- ZeroClaw runs as a background daemon in its own namespace with Linkerd sidecar
- Subscribed to Linkerd mesh tap data
- Monitors golden metrics (latency, error rate, throughput)
- If Linkerd reports >5% 5xx error rate for llm-gateway:
  - ZeroClaw initiates diagnostic loop
  - Checks local GPU health
  - Notifies opencode.ai (Teacher agent) if a workflow/class needs to be paused for repairs
- Auto-remediation: ZeroClaw triggers repair actions when circuit breakers trip or services fail

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
