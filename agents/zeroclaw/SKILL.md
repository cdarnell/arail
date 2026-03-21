# ZeroClaw SRE Skill

Purpose:
- ZeroClaw is the SRE/janitor agent framework responsible for observing, healing, and remediating cluster services.

Responsibilities:
- Monitor service health and metrics.
- Invoke `agent_escalator` for automated remediation with `--managed-by zeroclaw`.
- Maintain safe defaults (use `--safe-mode` when auto-applying commands).
- Record and export Prometheus metrics about escalations and recoveries.

Integration Points:
- Metrics: expose `/metrics` for Prometheus.
- Health checks: standard `/healthz` endpoint on each managed agent.
- Logs: write structured logs to `/var/log/zeroclaw/` and integrate with the lab logging stack.

Operational Commands:
- Start agent (systemd): `systemctl start zeroclaw.service`
- Run escalator for an agent: `agent_escalator --agent <id> --managed-by zeroclaw --health http://... --auto-apply --safe-mode`

Safety:
- ZeroClaw should default to `--safe-mode` and avoid destructive commands.
- All automatic remediations must be auditable and emitted to the observability pipeline.

Secrets: ZeroClaw uses HashiCorp Vault for its operational credentials and for storing user-provided tokens for services. ZeroClaw should authenticate to Vault via Kubernetes auth and use least-privilege policies. All actions that use sensitive credentials must read them from Vault at runtime (CSI or Vault Agent) and never log the raw values.
