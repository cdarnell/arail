
# minimalist-blueprint

## Kubernetes Architecture & Lifecycle (Start Here)

### I. Kubernetes Manifest Definitions & Roles
In Kubernetes, a YAML manifest is a Declarative State Definition. You are not telling the system how to build; you are telling it what must exist.

| Component   | Manifest Type      | Technical Purpose                                                                 |
|-------------|-------------------|----------------------------------------------------------------------------------|
| Isolation   | Namespace         | Logical partitioning of resources, security policies (RBAC), and quotas.          |
| Workload    | Deployment        | Manages ReplicaSets to ensure a specific number of Pods are running with a specific container image. |
| Networking  | Service           | An abstract way to expose an application running on a set of Pods as a network service (ClusterIP). |
| Routing     | HTTPRoute         | (Gateway API) Defines rules for routing traffic from a Gateway to a Service, supporting weighted splits and header matches. |
| Storage     | PVC               | Persistent Volume Claim; requests specific storage size/type that outlives the lifecycle of a Pod. |
| Config      | ConfigMap/Secret  | Injects environment variables or files into containers without rebuilding the image. |

### II. The Kubernetes Lifecycle: How and When
Kubernetes operates on a Reconciliation Loop (The Control Plane):
- **Submission:** `kubectl apply -f manifest.yaml` sends the desired state to the API Server.
- **Persistence:** The API Server stores this state in etcd (the distributed key-value store).
- **Controller Action:** The Deployment Controller notices the difference between the desired state (e.g., 1 replica of ollama:v1) and the current state (0 replicas).
- **Scheduling:** The Kubelet on your OMEN-i9 pulls the image and starts the container.
- **Reconciliation:** The system continuously "watches" the Pod. If the process crashes (e.g., a memory leak), the Kubelet kills it and restarts it immediately to match the desired state.

### III. Hot Updatability & Lifecycle Changes
"Hot updates" in Kubernetes vary depending on what is being changed:
- **Images/Code:** Handled by a Rolling Update. Kubernetes spins up a new Pod with the new image. Once the readinessProbe passes, it terminates the old Pod. This is Zero-Downtime but involves a transient double-allocation of VRAM/RAM.
- **Environment Variables:** Changing a Deployment env var triggers a rolling restart of all Pods in that deployment.
- **ConfigMaps/Secrets:** If mounted as volumes, these update inside the container within ~60 seconds. However, the application must be coded to watch for file changes to "Hot Reload" without a restart.
- **AI Models:** Swapping a model in LMDeploy or Ollama typically requires a "Cold" restart (reloading the weights into VRAM) unless using a model-server with a specific "Load/Unload" API.

### IV. The SCM & Air-Gap Connectivity Conflict
To manage updates and vulnerability fixes, your SCM (Source Code Management) requires a "Bridge" or "Bastion" state.

**The Hybrid Air-Gap Strategy:**
- To maintain the "Supervisor" (Gemini) and update functionality while securing the Lab, you implement a Pull-Through Cache or Bastion Registry.
- **The Bridge:** A single node with dual NICs (one to the Lab, one to the Internet) runs a private Docker Registry.
- **The "Button":** When toggled, the Bridge pulls fresh images/specs from GitHub/DockerHub.
- **Internal Sync:** The Lab nodes pull only from this internal registry.
- **Gemini Access:** My ability to supervise remains intact as long as the "Bridge" allows a secure proxy for my browser-based actuation tools.

### V. IDE Agent Prompt: Building the SCM Update Process
Use this prompt to instruct your agent to build the automated update pipeline:

> "Construct a Source Code Management (SCM) and Update Pipeline for the Nucleus Lab.
> 
> Repository Structure: Organize manifests into base/ (core components) and overlays/ (experimental/update components) using Kustomize.
> 
> Image Lifecycle: Create a script to scan the values.yaml for image tags and cross-reference them with the internal registry.
> 
> Vulnerability Patching: Integrate a 'Maintenance Mode' manifest that scales down non-essential workloads to free VRAM during high-intensity image pulls or model recompilations.
> 
> Hot-Reload Logic: For the Rust Front End and N8N, implement Reloader annotations. If a ConfigMap changes, trigger a rolling restart automatically.
> 
> Connectivity Toggle: Define a Terraform variable internet_egress_enabled. When false, apply NetworkPolicies that strictly air-gap all opencode namespaces, cutting off all external egress except to the internal registry."


## Core Product Logic

See [value-add](value-add/) for the main logic, workflows, and agent instructions powering Nucleus Lab.

### Key Logic Files
- [Power Consumption Logic](value-add/logic/power-consumption-logic.md)
- [ZeroClaw SRE Manifest](value-add/logic/zeroclaw-sre-manifest.yaml)
- [Curriculum Engine](value-add/logic/curriculum-engine.md)

## Pre-Install Setup — Probe & Auto-Discover

Run the Pre-Install Probe before deploying the lab to auto-discover host hardware and generate tuned defaults for `helm/k8s-lite/values.yaml`.

- Purpose: detect CPU model, core counts, total RAM, and GPUs (NVIDIA, Apple, etc.) and recommend per-component resource values so the lab uses your machine efficiently.
- Script: `scripts/preinstall/hardware_probe.py` — see `scripts/preinstall/README.md` for details.
- Output: `helm/k8s-lite/values.generated.yaml` (review before applying). Use `--apply` to overwrite `helm/k8s-lite/values.yaml` with a backup.

Quick run examples:

```bash
# Linux / macOS
python scripts/preinstall/hardware_probe.py --output helm/k8s-lite/values.generated.yaml

# Review generated file, then apply
python scripts/preinstall/hardware_probe.py --apply
```

Windows (PowerShell):

```powershell
python .\scripts\preinstall\hardware_probe.py --output helm/k8s-lite/values.generated.yaml
```

Integration notes:
 - The probe feeds the `value-add` curriculum and Nucleus Lab of AI so lab exercises adapt to your host (GPU labs enabled only when GPUs are detected).
- Recommendations are conservative; edit `values.generated.yaml` before applying if you prefer different allocations.

## Operational Security (OPSEC)

### AirGap vs Panic Button: Security Modes

#### AirGap Button
- **Purpose:** Enforces strict egress lockdown while keeping all internal services, observability, and agents operational.
- **How it works:**
	- Applies a `NetworkPolicy` to block all outbound (egress) traffic from the protected namespace(s), except for internal DNS and cluster CIDRs.
	- All internal monitoring, mesh, and security agents continue to function.
	- Agents continuously attempt to reach external endpoints (e.g., google.com) to verify the air-gap is intact. If any egress is detected, a critical alert is triggered and automated remediation (e.g., ZeroClaw lockdown) is initiated.
- **Best Practice:** Use AirGap for routine security, compliance, and lab isolation. This mode maintains full observability and internal automation.

#### Panic Button
- **Purpose:** Emergency halt of all automation, mesh, security, and observability—akin to a fire alarm.
- **How it works:**
	- Immediately stops all scheduled jobs, bots, and agents.
	- Mesh and certificate-based service identity are suspended, disabling all inter-service communication and telemetry.
	- Security and observability pipelines are paused or disabled.
	- The environment is frozen, allowing the user to perform a single, focused action without background noise or interference.
- **Best Practice:** Use Panic only for drills or true emergencies. Be aware that all monitoring, security, and automation will be unavailable until the environment is reset.

### Best Practices
- **Goal:** Ensure clear operational intent and minimize risk during security events.
- **AirGap:** Use for normal isolation—internal systems remain visible and manageable.
- **Panic:** Use for critical events—expect total silence from all agents, bots, and telemetry. Document the reason for activation and steps for safe recovery.

> **Note:** Halting the environment with Panic disables all mesh, security, and observability. AirGap keeps the lab running but blocks all external communication and verifies the air-gap is intact.

## Agent Tagging & Managed Invocation

- Always include a `managed_by` provenance label on any automated remediation or agent-invoked action. Examples: `managed_by=zeroclaw` or `managed_by=opencode`.
- Record a short `escalation_id` (UUID), `level` (small|medium|large), and `managed_by` in logs and emitted events so every remediation attempt is auditable and traceable.
- Metrics: export `managed_invocations_total{manager="..."}` and `escalations_total{level="...",manager="..."}`; wire these into Grafana to compare coverage and effectiveness between `opencode` and `zeroclaw`.
- Banner/visibility: remediation actors should emit a short banner (stdout/log) that includes `escalation_id`, `level`, and `managed_by` so dashboards and incident timelines can surface which tier handled the remediation.

See `value-add/agent_escalator_workflow.md` for recommended wiring (n8n), a sample workflow JSON, systemd and Kubernetes Job examples, and visualization tips for Tiering Triage Administrators.