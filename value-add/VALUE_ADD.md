# Power-Aware Cost Simulator Logic

## Overview
This simulator quantifies the cost of running local LLM inference versus using cloud APIs, based on power consumption and API pricing.

- **Default Power Cost:** $0.10/kWh (local)
- **Cloud API Cost:** Variable, based on provider pricing

### Workflow
1. Measure inference duration and wattage
2. Calculate local power cost: 
   $$\text{Cost} = \frac{\text{Wattage} \times \text{Duration (hours)}}{1000} \times \$0.10$$
3. Compare to API cost per token/request
4. Output savings or cost difference

### Example Calculation
- Local GPU: 200W, 1 hour inference
- Local cost: $0.10/kWh × (200W × 1h / 1000) = $0.02
- Cloud API: $0.01 per 1,000 tokens

### Agent Roles
- **opencode.ai (Teacher/Orchestrator):** Explains calculations, optimization tips, and workflow logic.
- **zeroclaw (Janitor/SRE):** Monitors infrastructure, triggers cost-saving actions, and auto-remediation.

---

## Persona Mapping
- **opencode.ai:** Teacher/Orchestrator
- **zeroclaw:** Janitor/SRE (Infrastructure)

---

## Next Steps
- Add new goals and workflows as Markdown files in this directory.
- Document agent instructions for each value-add goal.

Mastra AI & Pydantic Integration
- **Overview:** This repository now includes an agent orchestration pattern using Mastra AI as the control plane and Pydantic (pydantic-ai) as the pre-execution validation layer. The control plane validates requests (schema, resource limits, allowed libs) to reject invalid work before provisioning transient pods.
- **Execution Strategy:** Models are pre-warmed into a host-backed shared location on single-node Linux clusters. Transient worker pods mmap weights for sub-second startup and zero redundant RAM usage.
 - **Service Mesh:** Design assumes Linkerd (sidecar-based) to provide mTLS and proxy-level telemetry via `linkerd2-proxy` sidecars while keeping overhead low.
- **Observability:** Mastra Studio monitors logical flows (validation → handoff); Grafana/Tempo capture node-level and eBPF telemetry.

See `helm/k8s-lite` for chart-level templates and the sample Mastra manifests added under `helm/k8s-lite/templates/ai/`.

Shared-Memory mmap Pattern (Transient Python Workers)
- **Core Idea:** Use an `emptyDir` volume with `medium: Memory` to host pre-warmed model weights on the node. A one-time loader populates this memory-backed volume; transient Python pods mount it and access weights via `mmap`, achieving zero-copy, instant model access.
- **Gold Image:** Build a minimal, precompiled Python base image (distroless or slim) containing precompiled `.pyc` files and required C-extensions (PyTorch / llama-cpp-python). Avoid `pip install` at runtime.
 - **Service Mesh:** Linkerd (sidecar-based) provides mTLS and proxy-level telemetry; per-pod sidecar injection is used instead of Istio-style Ambient sidecarless operation.
- **Validation & Dispatch:** Mastra performs Pydantic validation; only valid tasks trigger transient pods via the Kubernetes API.

Minimal Pod YAML example (mounts shared memory-backed model store):

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
            memory: "2Gi" # Limit for the logic, not the model
   volumes:
   - name: model-store
      emptyDir:
         medium: Memory # This maps directly to your host's RAM
```

Benefits
- Zero Duplication: Multiple transient pods share the same physical RAM holding the model weights.
- Sub-second Starts: Removing the sidecar and model-load phases yields near-instant execution.
- Low Complexity: No need for heavyweight model servers — standard Kubernetes volumes and mmap suffice for efficient transient execution.
