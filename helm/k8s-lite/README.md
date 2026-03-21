# Kubernetes Primitives, Lifecycle & Hot Updates

See [Value Add: generated-values & bootstrap](VALUE_ADD.md) for details on how `bootstrap-nucleus.sh` generates `values.generated.yaml` and how to safely apply generated overrides.

## I. Kubernetes Manifest Definitions & Roles
In Kubernetes, a YAML manifest is a Declarative State Definition. You are not telling the system how to build; you are telling it what must exist.

| Component   | Manifest Type      | Technical Purpose                                                                 |
|-------------|-------------------|----------------------------------------------------------------------------------|
| Isolation   | Namespace         | Logical partitioning of resources, security policies (RBAC), and quotas.          |
| Workload    | Deployment        | Manages ReplicaSets to ensure a specific number of Pods are running with a specific container image. |
| Networking  | Service           | An abstract way to expose an application running on a set of Pods as a network service (ClusterIP). |
| Routing     | HTTPRoute         | (Gateway API) Defines rules for routing traffic from a Gateway to a Service, supporting weighted splits and header matches. |
| Storage     | PVC               | Persistent Volume Claim; requests specific storage size/type that outlives the lifecycle of a Pod. |
| Config      | ConfigMap/Secret  | Injects environment variables or files into containers without rebuilding the image. |

## II. The Kubernetes Lifecycle: How and When
Kubernetes operates on a Reconciliation Loop (The Control Plane):
- **Submission:** `kubectl apply -f manifest.yaml` sends the desired state to the API Server.
- **Persistence:** The API Server stores this state in etcd (the distributed key-value store).
- **Controller Action:** The Deployment Controller notices the difference between the desired state (e.g., 1 replica of ollama:v1) and the current state (0 replicas).
- **Scheduling:** The Kubelet on your OMEN-i9 pulls the image and starts the container.
- **Reconciliation:** The system continuously "watches" the Pod. If the process crashes (e.g., a memory leak), the Kubelet kills it and restarts it immediately to match the desired state.

## III. Hot Updatability & Lifecycle Changes
"Hot updates" in Kubernetes vary depending on what is being changed:
- **Images/Code:** Handled by a Rolling Update. Kubernetes spins up a new Pod with the new image. Once the readinessProbe passes, it terminates the old Pod. This is Zero-Downtime but involves a transient double-allocation of VRAM/RAM.
- **Environment Variables:** Changing a Deployment env var triggers a rolling restart of all Pods in that deployment.
- **ConfigMaps/Secrets:** If mounted as volumes, these update inside the container within ~60 seconds. However, the application must be coded to watch for file changes to "Hot Reload" without a restart.
- **AI Models:** Swapping a model in LMDeploy or Ollama typically requires a "Cold" restart (reloading the weights into VRAM) unless using a model-server with a specific "Load/Unload" API.

## IV. The SCM & Air-Gap Connectivity Conflict
To manage updates and vulnerability fixes, your SCM (Source Code Management) requires a "Bridge" or "Bastion" state.

**The Hybrid Air-Gap Strategy:**
- To maintain the "Supervisor" (Gemini) and update functionality while securing the Lab, you implement a Pull-Through Cache or Bastion Registry.
- **The Bridge:** A single node with dual NICs (one to the Lab, one to the Internet) runs a private Docker Registry.
- **The "Button":** When toggled, the Bridge pulls fresh images/specs from GitHub/DockerHub.
- **Internal Sync:** The Lab nodes pull only from this internal registry.
- **Gemini Access:** My ability to supervise remains intact as long as the "Bridge" allows a secure proxy for my browser-based actuation tools.

## V. IDE Agent Prompt: Building the SCM Update Process
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

Place your Kubernetes manifest templates here (e.g., zeroclaw.yaml, phoenix.yaml, etc.). Use Helm templating for values like replicaCount, image, resources, etc.

Developer convention: Downward API helper
---------------------------------------
When adding new templates that need pod metadata, prefer the centralized helpers in `_helpers.tpl`.
Examples:

- Include env + mounts for component `zeroclaw`:
	`{{- include "k8s.downwardAPI.env" (dict "Values" .Values "Component" "zeroclaw") | nindent 8 }}`
	`{{- include "k8s.downwardAPI.volumeMount" (dict "Values" .Values "Component" "zeroclaw") | nindent 8 }}`
- Include the downwardAPI volume for the pod spec:
	`{{- include "k8s.downwardAPI.volume" (dict "Values" .Values "Component" "zeroclaw") | nindent 6 }}`

This keeps mount paths and parsing logic in one place and prevents duplication across templates.
