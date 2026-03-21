# Agent Escalator Workflow — Tiering Triage Administrators

This document describes how to wire `agent_escalator` into the lab workflows, recommended n8n wiring, sample workflow JSON, systemd / Kubernetes job examples, and metrics/dashboard guidance.

## Overview
- Purpose: provide a predictable, auditable, tiered remediation flow where `opencode` handles first-line, low-cost fixes and `zeroclaw` manages SRE-level escalations.
- Provenance: every invocation must include `managed_by` and generate an `escalation_id`.
- Visibility: metrics and logs must show which manager invoked remediation and which tier succeeded.

## Recommended n8n wiring (concept)
1. Trigger: HTTP webhook (from service, gateway, or alertmanager) or scheduled health probe event.
2. Gather context: fetch recent logs, traces, Pod status, and metrics.
3. Decision node: if issue is application-only, attempt opencode self-remediation; else route to ZeroClaw.
4. Remediation attempt(s): call local ops (HTTP to service management endpoints, run safe commands), re-check health.
5. If still failing, call `agent_escalator` (HTTP wrapper or remote exec) with `managed_by=opencode`.
6. Stream results back; if unresolved, open incident and route to `managed_by=zeroclaw` for deeper escalation.

## Sample n8n HTTP workflow (minimal)
- This example assumes you expose a thin HTTP wrapper for `agent_escalator` (or an SSH/Exec node that runs it directly). Replace `http://escalator.local:9000/escalate` with your actual endpoint.

```json
{
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "url": "http://escalator.local:9000/escalate",
        "options": {},
        "bodyParametersJson": "={{ JSON.stringify({ agent: $json.agentId, health: $json.healthUrl, managed_by: 'opencode', auto_apply: false, safe_mode: true }) }}"
      },
      "name": "Call Agent Escalator",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 1,
      "position": [600, 300]
    }
  ],
  "connections": {}
}
```

Notes:
- If you prefer direct execution, use the `Execute Command` or `SSH` node to run `agent_escalator --agent <id> --managed-by opencode ...` on a trusted runner.
- Ensure the n8n credential used to run commands is restricted and auditable.

## systemd unit example (for local runner)

```
[Unit]
Description=Agent Escalator Runner
After=network.target

[Service]
Type=simple
User=ops
ExecStart=/usr/local/bin/agent_escalator --managed-by zeroclaw --health http://localhost:9000/healthz
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## Kubernetes Job (example)

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: agent-escalator-job
spec:
  template:
    spec:
      containers:
      - name: agent-escalator
        image: registry/local/agent_escalator:latest
        args: ["--agent", "{{AGENT_ID}}", "--managed-by", "zeroclaw", "--health", "http://service:9000/healthz"]
      restartPolicy: Never
  backoffLimit: 2
```

Integration
- For full integration the platform must bake Downward API and Vault-aware configuration into deployed workloads. Implementation details in this repo include:
  - Helm templates updated to mount the Downward API (pod name, namespace, labels) into agent pods so agents can auto-derive Vault roles and provenance.
  - `agent_escalator` supports Kubernetes-auth Vault login and will read the in-cluster JWT and derive a role from the pod `app` label or namespace when `--vault-k8s-role` is not provided.
  - Deployment and Job templates in `helm/minimalist/templates/` now include conditional Downward API mounts controlled by `agentEscalator.downwardAPI.enabled` in `values.yaml`.

- The integration assumes Vault is used only for secrets (KV, dynamic creds, tokens). TLS and Linkerd mTLS are managed by the mesh and cluster configuration; the platform does not use Vault for cert/passphrase lifecycle in this flow.

Operationally: the provisioning scripts and Helm values in `provisioning/vault/` automate installing Vault, creating roles/policies, and wiring the Kubernetes auth flow so the user does not need to perform these steps manually.

## Banner / Visibility
- The program should write a short structured banner to logs when running an escalation, e.g.:

```
[escalation] id=123e4567 level=medium managed_by=opencode message="starting remediation"
```

- Grafana panels should parse logs / events and display the active `level` and `managed_by` in incident timelines.

## Metrics & Dashboards
- Ensure Prometheus scrapes the `agent_escalator` and agents.
- Key metrics:
  - `managed_invocations_total{manager="opencode|zeroclaw"}`
  - `escalations_total{level="small|medium|large", manager="..."}`
  - `recoveries_total{level="...", manager="..."}`
  - `commands_executed_total{level="..."}`
- Suggested panels:
  - Side-by-side: Escalations by manager (bar), Recovery rate by manager (line), MTTR by manager (single stat)
  - Timeline: incidents with `escalation_id`, showing which manager attempted remediation and which level succeeded

## Auditing & Safety
- Default to `--safe-mode` in automated flows. Only allow `--auto-apply` behind an approval node.
- Record all executed commands in the logging backend and attach to `escalation_id` for postmortem.

## Storage & Value-Add
- Save the n8n JSON workflows in `value-add/n8n/` for version control and reuse.
- This file documents the recommended flow and example artifacts for Tiering Triage Administrators.
