# React Dashboard Routes & Endpoints

| Route         | Description                                 | UI/Integration                |
|---------------|---------------------------------------------|-------------------------------|
| /             | Main dashboard, service health, Grafana     | Grafana embed, status cards   |
| /notebook     | Open Notebook UI (custom .ipynb editor)     | React notebook component      |
| /jupyterlab   | JupyterLab interface (via Jupyter API)      | JupyterLab iframe/proxy       |
| /grafana      | Grafana dashboards (embedded)               | Grafana iframe/embed          |

## Notes
- The dashboard should allow switching between Open Notebook and JupyterLab.
- All endpoints are protected by Linkerd mesh (mTLS, zero-config security) and instrumented with OpenTelemetry SDK for tracing and metrics (W3C header propagation).
- Service health checks should poll Prometheus or service endpoints.

---

*Update as new routes or integrations are added.*
