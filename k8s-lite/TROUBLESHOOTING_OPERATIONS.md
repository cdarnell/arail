## 5. API Standardization & OpenAPI Troubleshooting

- **Validate OpenAPI Specs:**
  - Ensure every service exposes a valid OpenAPI (Swagger) spec at a discoverable endpoint or file path (see inventory for locations).
  - Use tools like Swagger UI, Redoc, or `openapi-generator-cli validate` to check spec validity.
  - Example validation command:
    ```sh
    npx openapi-generator-cli validate -i /path/to/openapi.yaml
    ```
- **API Discovery:**
  - All APIs should be listed in the service inventory with their OpenAPI spec path.
  - Use the OpenAPI spec to generate client SDKs, documentation, and integration tests.
- **Adding/Updating APIs:**
  - When adding a new API, provide an OpenAPI spec and update the inventory and documentation.
  - For existing APIs, retrofit with OpenAPI and validate before deployment.

# Minimalist AI Lab: Troubleshooting & Operations Guide

## 1. Checking Pod and Service Status

- List all pods in all namespaces:
  ```sh
  kubectl get pods -A
  ```
- Get detailed status for a specific pod:
  ```sh
  kubectl describe pod <pod-name> -n <namespace>
  ```
- View logs for a pod:
  ```sh
  kubectl logs <pod-name> -n <namespace>
  ```
- List all services:
  ```sh
  kubectl get svc -A
  ```
- Check deployments and statefulsets:
  ```sh
  kubectl get deploy,statefulset -A
  ```

## 2. Mesh, Telemetry, and Observability

- Check Linkerd mesh health:
  ```sh
  linkerd check
  linkerd viz stat deployments -A
  linkerd viz edges deploy -A
  ```
- Verify Prometheus is scraping all targets:
  - Access Prometheus UI (default: `http://<prometheus-service>:9090`)
  - Go to **Status > Targets**
- Check Grafana dashboards:
  - Access Grafana UI (default: `http://<grafana-service>:3000`)
  - Import `ai-lab-unified-dashboard.json` for unified observability
- Check Phoenix LLM traces:
  - Access Phoenix UI (default: `http://<phoenix-service>:6006`)

## 3. Event Bus and Workflow

- Check Redpanda (Kafka) status:
  ```sh
  kubectl get pods -n redpanda
  # Use Redpanda admin API on :9644 for health
  ```
- Check n8n workflow status:
  - Access n8n UI (default: `http://<n8n-service>:5678`)

## 4. Common Issues & Fixes

- **Pod CrashLoopBackOff:**
  - Check logs (`kubectl logs ...`)
  - Check events (`kubectl describe pod ...`)
  - Verify resource limits and storage
- **Service Unavailable:**
  - Check service endpoints (`kubectl get endpoints -A`)
  - Check mesh injection and mTLS status
- **No Metrics/Traces:**
  - Verify Prometheus scrape config
  - Check OpenTelemetry Collector and service annotations

## 5. Useful Commands

- Restart a deployment:
  ```sh
  kubectl rollout restart deployment <name> -n <namespace>
  ```
- Port-forward a service:
  ```sh
  kubectl port-forward svc/<service> <local-port>:<service-port> -n <namespace>
  ```
- Get all namespaces:
  ```sh
  kubectl get ns
  ```

---

Keep this guide updated as the stack evolves. For advanced debugging, consult the documentation for each component (Linkerd, Prometheus, Grafana, Redpanda, etc.).
