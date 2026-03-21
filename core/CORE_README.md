# 🛑 STOP: The Nucleus Baseline

This lab is pre-configured with the **Nucleus Core**.

- **Security:** mTLS is forced. Do not attempt to use plain HTTP between services.
- **Observability:** If it isn't traced, it didn't happen. Use the provided `traceparent` headers.
- **Mentorship:** Your Resident Agent is already watching the logs. Ask it "How is the health of my mesh?" to start.

## What is the Nucleus Core?
The Nucleus Core is the immutable baseline for every user. It ensures:
- True Observability (OpenTelemetry, W3C headers, Prometheus, Grafana)
- Rubber Stamp Security (Linkerd mTLS, mesh DNS)
- Resource-aware sizing and auto-profiling
- All services are monitored and traced by default

## Directory Structure
```
core/
  infrastructure/
    k3s-init.sh
    linkerd-install.sh
  observability/
    otel-collector.yaml
    grafana-dashboards/
  defaults/
    resource-profiles.yaml
    global-values.yaml
```

## Default Setup Logic
- Resource-aware sizing: scripts auto-detect RAM/CPU and select the right profile
- Observability stamp: mesh and metrics are injected automatically
- W3C header propagation: all services pass trace context by default
