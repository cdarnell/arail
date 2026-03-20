# Directory Structure

```
react-dashboard/
	package.json
	tsconfig.json
	vite.config.ts
	README.md
	public/
	src/
		App.tsx
		index.tsx
		theme.css
		components/
			DashboardClient.tsx
			ServiceHealth.tsx
			ChatWidget.tsx
			ZeroClawPanel.tsx
			ResearchPanel.tsx
			NotebookPanel.tsx
			JupyterLabPanel.tsx
			GrafanaEmbed.tsx
			WireframeBoundary.tsx
		routes/
			index.tsx
			notebook.tsx
			jupyterlab.tsx
			grafana.tsx
```
# React Dashboard for Gentoofoo AI Lab

This dashboard provides:
- At-a-glance observability (Grafana integration)
- Notebook access: Open Notebook UI and JupyterLab (via Jupyter Server API)
- Service status and metrics (powered by OpenTelemetry and Linkerd mesh)

## Features
- **Open Notebook**: Custom notebook editor/viewer for .ipynb files
- **JupyterLab**: Launches full JupyterLab interface via API
- **Grafana Embeds**: Visualize AI Lab metrics
- **Service Health**: Show status of core services (LMDeploy, Opencode, n8n, Kafka, etc.)
- **Tracing & Metrics**: All services instrumented with OpenTelemetry SDK (W3C header propagation) and run in Linkerd mesh for secure, observable traffic.

## Endpoints
- `/notebook` — Open Notebook UI
- `/jupyterlab` — JupyterLab interface (proxied)
- `/grafana` — Embedded Grafana dashboards

## Example Usage
- Click "Open Notebook" to edit .ipynb files in-app
- Click "JupyterLab" for full Jupyter experience
- View metrics and service health on the main dashboard

---

**Note:** All new services must use the OpenTelemetry SDK for W3C header propagation and correlated spans to Grafana (Tempo/Jaeger). Tracing is a key requirement; OpenTelemetry must be used with W3C native format. Linkerd is the required service mesh.

*Scaffold the React app with these routes and embed the required UIs for the initial release.*
