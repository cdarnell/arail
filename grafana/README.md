# Grafana Dashboards for Minimalist AI Lab

This folder contains Grafana dashboards you can import into your Grafana instance.

Included:

- `ai-lab-heatmap-dashboard.json` — main dashboard with service heatmap, GPU power, cost estimate, traces (Tempo), logs (Loki), remote cost table, and quick actions.

Import instructions:

1. Open Grafana -> Dashboards -> Import.
2. Upload `ai-lab-heatmap-dashboard.json` or paste its contents.
3. When prompted, select your Prometheus datasource and Tempo/Loki datasources.
4. Adjust panel queries if your metric names differ (see `value-add/design.yml` for expected metric names such as `node_gpu_power_watts`, `service_request_duration_seconds_sum`).

Provisioning (auto-mapping datasources):

- This repo includes example Grafana provisioning files under `grafana/provisioning/` for automatic datasource and dashboard import. Copy these into your Grafana container at `/etc/grafana/provisioning/` and the dashboard files into `/var/lib/grafana/dashboards/ai-lab/`.
- Provided provisioning files:
	- `provisioning/datasources/prometheus.yaml` — Prometheus datasource (name: `Prometheus`).
	- `provisioning/datasources/loki.yaml` — Loki datasource (name: `Loki`).
	- `provisioning/datasources/tempo.yaml` — Tempo datasource (name: `Tempo`).
	- `provisioning/dashboards/dashboards.yaml` — dashboard provider that loads dashboards from `/var/lib/grafana/dashboards/ai-lab`.

Example Docker run (mount provisioning and dashboards):

```bash
docker run -d \
	-p 3000:3000 \
	-v $(pwd)/grafana/provisioning:/etc/grafana/provisioning:ro \
	-v $(pwd)/grafana/dashboards:/var/lib/grafana/dashboards:ro \
	grafana/grafana:latest
```

Or use your cluster's Grafana Helm chart to mount these files as configMap/volume; ensure datasource names match the dashboard expectations (Prometheus, Loki, Tempo).

Notes:

- Ensure Tempo, Prometheus, and Loki are configured as datasources in Grafana before import.
- The Quick Actions panel includes links; replace `http://aag.example.local` with your actual AAG access URL.
- The Kill -9 action is a UI convention here — implement backend endpoint `/api/observability/kill` with RBAC enforcement to perform the actual pod deletion.

*** End File