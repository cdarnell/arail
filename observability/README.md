# Observability Constitution (Mandatory)

> **No service shall be deployed 'Dark.'**

### 1. Instrument the Lungs
- Every service manifest (n8n, LMDeploy, etc.) **must** include:
   - `prometheus.io/scrape: "true"`
   - `linkerd.io/inject: enabled`
   (Add as annotations to every Deployment/Service.)

### 2. Standardize the Syllabus
- Every component **must** expose:
   - `/healthz` (health check endpoint)
   - `/metrics` (Prometheus metrics endpoint)
   (If missing, deployment is a failure.)

### 3. The Janitor's Vision
- ZeroClaw must alert the Zellij Heart terminal if any service success rate drops below 99%.
   - Configure Prometheus Alertmanager and ZeroClaw integration for this.

### 4. Textbook Standard
- Every API **must** serve an `openapi.json` spec at a discoverable endpoint.
   - This is required for Supervisor automation and integration.

---

# The Nucleus Academy (Linkerd Edition)
# Project Schoolhouse — Observability Stack Configuration

## Executive Summary
The Nucleus Academy is a "Lab-in-a-Box" for AI learning and experimentation, designed for high-efficiency local deployment. Its core value is the presence of AI instructors—resident mentor agents—who help you LEVEL UP by providing contextual guidance, workflow suggestions, and hands-on learning. Autoresearch and simulated spend are value-add features, but the real differentiator is the Academy’s focus on continuous skill development and AI-powered mentorship.

---

## Architecture

See `architecture.mmd` (Mermaid diagram) for a visual overview. Render with Mermaid.js or VS Code Mermaid extension.

## Key Requirements (Technical)
- **Service Mesh**: Linkerd (Rust-based, mTLS, zero-config security, built-in Viz dashboard)
- **Tracing**: All services must use the OpenTelemetry SDK with W3C header propagation for correlated spans. Tracing is a key integration point.
- **Collectors**: OpenTelemetry Collectors must send traces to both Prometheus and Tempo/Jaeger.
- **OpenAPI Standardization**: Every API in the lab **must** provide an OpenAPI (Swagger) specification. This ensures all endpoints are discoverable, documented, and support seamless integration and scaling. All new services and endpoints must be designed OpenAPI-first, and existing APIs should be retrofitted with OpenAPI specs.
- **Mentor Agent**: The observability stack is designed to support the resident mentor agent, ensuring all metrics, traces, logs, and API documentation are available for both operational insight and user learning/level-up guidance.
## API Standardization & Example: Learning API

All APIs must be documented with OpenAPI. Example Learning API endpoints (to be included in the OpenAPI spec for the Learning Agent):

| Method | Path                        | Description                                 |
|--------|-----------------------------|---------------------------------------------|
| GET    | /learning/suggestions       | Get personalized learning suggestions       |
| GET    | /learning/explain/{component} | Get an explanation for a specific component |
| GET    | /learning/next-steps        | Get recommended next steps for the user     |
| POST   | /learning/feedback          | Submit user feedback on learning experience |
| GET    | /learning/progress          | Get the user's learning progress            |

**All new APIs must:**
- Provide a valid OpenAPI spec (YAML or JSON)
- Be accessible for automated discovery and integration
- Include example requests/responses in the spec
- Be referenced in service documentation and troubleshooting guides

**OpenAPI specs should be stored alongside each service and referenced in the inventory.**


## Deployment Assumptions
- **K3s** (single node, installed with `--disable traefik`)
- **Linkerd** for service mesh (Rust proxy, mTLS, zero-config security, Viz dashboard)
- **OpenTelemetry**: SDK required in all services for W3C header propagation and tracing
- **Observability**: Prometheus, Grafana, Loki, Tempo/Jaeger, Alertmanager
- **Orchestration**: All manifests are for Kubernetes, single-node, resource-efficient

## Quickstart
1. Install K3s (single node):
   ```sh
   curl -sfL https://get.k3s.io | sh -s - --disable traefik
   ```
2. Install Linkerd (see Linkerd docs)
3. Apply manifests in this directory:
   ```sh
   kubectl apply -f prometheus-deployment.yaml
   kubectl apply -f grafana-deployment.yaml
   kubectl apply -f loki-deployment.yaml
   kubectl apply -f tempo-deployment.yaml
   # Add Alertmanager, OpenTelemetry Collector, and exporters as needed
   ```
4. Access Grafana at https://grafana.gentoofoo.com (configure ingress/proxy as needed)

## Notes
- All components run in the `observability` namespace
- Prometheus scrapes metrics from all mesh workloads, Linkerd proxies, and exporters
- Grafana, Loki, and Tempo/Jaeger are pre-wired for logs and traces
- OpenTelemetry Collector is required for trace and metrics collection
- Alertmanager is recommended for alerting (add manifest)

---

Update this README as the stack evolves or if you add more exporters, dashboards, integrations, or APIs. **All new services must provide an OpenAPI spec, expose /healthz and /metrics, and use the OpenTelemetry SDK for W3C header propagation and correlated spans to Grafana (Tempo/Jaeger).** The Nucleus Academy’s core value is the AI-powered learning experience—autoresearch and simulated spend are value-add, but the resident mentor agent is the differentiator.
