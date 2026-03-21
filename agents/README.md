# Agents Directory

This folder contains agent framework documentation and skill files. Each agent has its own subdirectory with a SKILL.md describing responsibilities, integration points, and operational commands.

Structure:
- `agents/zeroclaw/` — ZeroClaw SRE agent framework (manages restarts, healing, remediation flows).
- `agents/opencode/` — Core opencode agent (application-facing agents that perform domain tasks).

Metrics and observability:
- Each agent should expose a `/metrics` endpoint for Prometheus scraping.
- `agent_escalator` records which manager invoked remediation via `managed_invocations_total{manager="..."}`.

Management:
- Use the `managed_by` CLI arg on tools to indicate which agent invoked an action.
- Place agent-specific scripts, systemd unit files, and k8s manifests inside the agent subdirectory.
