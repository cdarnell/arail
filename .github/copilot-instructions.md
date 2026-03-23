# Nucleus AI Lab: Core Architecture & Identity
    - **Purpose:** A minimalist, self-refining AI Lab-in-a-Box running on K3s (Ubuntu/WSL).
    - **Security & Identity:** Uses HashiCorp Vault with Kubernetes-native auth. 
    - **Zero-Trust Metadata:** Leverages the K8s Downward API to mount pod labels at `/etc/podinfo`. Agents MUST use these labels to derive their Vault roles (e.g., '<namespace>-<app>-role') instead of static tokens.
    - **Mission-First Philosophy:** The lab is 'The Art of the Possible.' Everything revolves around a user-defined 'Goal' (e.g., Quantum Synchronicity or SRE Resilience).
    - **Agent Roles:** - 'Resident Mentor': Provides real-time, goal-aware IDE guidance.
      - 'Teacher Agent': Tailors curriculum based on the 'Major' defined in Helm values.
    - **Observability:** Integrated Linkerd mesh, Prometheus, Grafana, and Loki for 'True Observability' of agent behavior and system 'vibrations.'
