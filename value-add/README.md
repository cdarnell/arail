# Defining Value-Add Goals and Deterministic Workflows

## Purpose
The `value-add` directory is for user-defined goals that drive deterministic workflows, enabling opencode agents and the "AI Teacher" to assist, explain, and automate value creation.

---

## How to Define a Value-Add Goal
1. **Describe the Goal Clearly:**
   - What outcome do you want? (e.g., "Reduce LLM inference cost below API pricing.")
   - Why is this valuable? (e.g., "To optimize infrastructure spend and increase transparency.")
2. **Specify Inputs and Constraints:**
   - What data, metrics, or context is required?
   - Are there standards, thresholds, or best practices to follow?
3. **Trigger a Deterministic Workflow:**
   - Each goal should kick off a workflow (manual or automated) that:
     - Gathers required data
     - Runs logic or analysis
     - Produces actionable outputs (reports, alerts, dashboards, etc.)
4. **Instruction Sets for Opencode Agents:**
   - For each goal, define what the agents should do:
     - What to automate
     - What to explain ("AI Teacher" role)
     - What to document/share

---

## Example: LLM Power Consumption vs API Cost
- **Goal:** Quantify and compare the cost of local LLM inference to API usage.
- **Workflow:**
  1. Collect inference duration, wattage, and token count
  2. Calculate power cost and compare to API cost
  3. Output result and explanation
- **AI Teacher:**
  - Explains each calculation step
  - Shares optimization tips (e.g., "Try batch inference to reduce cost per token.")
  - Documents findings for future reference

---

## Pre-Installation Flight Check: Hardware-Aware Auto-Tuning
- **Goal:** Automatically scan the host hardware (CPU, GPU, RAM) before installation and set best-practice resource values for each LAB component in `values.yaml`.
- **Workflow:**
  1. Pre-install script detects CPU model (e.g., i9), GPU (e.g., 3090 NVIDIA), and total RAM.
  2. Script generates or updates `values.yaml` with recommended `resources` for each component (CPU, memory, GPU, and key environment variables).
  3. Each component's section in `values.yaml` is annotated with meta-data and best-practice values for the detected hardware.
  4. User can review and override before install proceeds.
- **Example Table:**

| Component   | CPU Request/Limit | RAM Request/Limit | GPU Limit | Note |
|-------------|-------------------|-------------------|-----------|------|
| Ollama      | 1 / 2 Cores       | 2Gi / 4Gi         | 1         | Handles "General" model tasks. |
| LMDeploy    | 2 / 4 Cores       | 4Gi / 8Gi         | 1         | The "High-Speed" production engine. |
| n8n         | 0.5 / 1 Core      | 1Gi / 2Gi         | 0         | The "Teacher" orchestrating the loop. |
| Redpanda    | 1 / 2 Cores       | 1Gi / 2Gi         | 0         | The "Intercom" (Set memory: 1Gi for cache). |
| Jupyter/Zellij | 0.5 / 1 Core   | 512Mi / 1Gi       | 0         | The "Workshop" where you write Rust/Python. |
| Prometheus  | 0.5 / 1 Core      | 1Gi / 2Gi         | 0         | Retention: Set to 15d to save disk space. |

- **AI Teacher:**
  - Explains why each resource value is chosen for your hardware
  - Documents the scan and recommendations in a report
  - Ensures the LAB takes full advantage of available cores, memory, and GPU

---

## Why This Approach?
- Ensures every value-add is transparent, reproducible, and teachable
- Empowers users to define, measure, and improve what matters most
- Makes agent assistance explainable and actionable

---

## Next Steps
- Add new goals as Markdown files in this directory
- For each, define the workflow and agent instructions
- The "AI Teacher" will always:
  - Share how things are done
  - Suggest what could be done
  - Explain why things are done this way

---

## Preinstall Hardware Probe

We've added a cross-platform pre-installation script that detects host hardware and generates recommended `values.yaml` resource values for the Minimalist lab.

- Location: `scripts/preinstall/hardware_probe.py`
- Requirements: `scripts/preinstall/requirements.txt` (`pyyaml`, `psutil`)
- Output: `helm/k8s-lite/values.generated.yaml` (use `--apply` to overwrite `helm/k8s-lite/values.yaml` with a backup)

This tool is designed to be friendly for non-experts and supports macOS, Windows, and Linux host environments. It recommends CPU, memory, and GPU allocations for core components and documents the choices in the generated YAML.

---

## Nucleus School of AI

Nucleus School of AI is the instructional layer bundled with the Minimalist lab. It translates the lab's capabilities into guided learning paths, making the platform accessible to beginners while retaining depth for advanced users.

- **Core Offerings:**
  - Guided labs mapped to real infra tasks (deploy models, tune resources, run observability checks).
  - The **AI Teacher**: an explainable assistant that walks users through steps, explains trade-offs, and generates reproducible reports.
  - Playbooks, checklists and assessment labs for safe, repeatable learning.

- **Curriculum Highlights:**
  - Fundamentals: Kubernetes basics, service mesh, observability, and safety modes (AirGap vs Panic).
  - Practical labs: model deployment (`lmdeploy`, `ollama`), pipeline orchestration (`n8n`), and telemetry management (Prometheus/Loki/Grafana).
  - Assessments with automated verification and feedback from the AI Teacher.

- **Integration & Personalization:**
  - Uses the preinstall hardware probe to tailor lab exercises to the host (e.g., enabling GPU labs only when GPUs are present).
  - Exposes the rationale behind recommended `values.yaml` settings and offers safe override guidance for power users.

- **Sharing & Community:**
  - Exportable lab snapshots and reproducible recipes for sharing with peers.
  - Friendly language and UI cues to reduce accidental misconfiguration for non-technical users.

Nucleus School of AI converts powerful tooling into teachable, safe, and repeatable experiences—an important value-add when sharing the lab with friends, family, or students.
