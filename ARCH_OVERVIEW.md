# Nucleus Lab Architecture Overview

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
