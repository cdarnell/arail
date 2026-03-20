
# The Nucleus Academy (Linkerd Edition)
# Project Schoolhouse — Service Inventory & Observability

## Executive Summary
The Nucleus Academy is a "Lab-in-a-Box" for AI learning and experimentation, designed for high-efficiency local deployment. Its core value is the presence of AI instructors—resident mentor agents—that help you LEVEL UP by providing contextual guidance, workflow suggestions, and hands-on learning. Autoresearch and simulated spend are value-add features, but the real differentiator is the Academy’s focus on continuous skill development and AI-powered mentorship.


| Service           | Core Function                                      | Example Endpoint / Usage                | OpenAPI Spec Path                      |
|-------------------|---------------------------------------------------|-----------------------------------------|----------------------------------------|
| LMDeploy          | LLM inference, token usage, metrics (advanced/optional) | POST /generate, GET /metrics            | /openapi/lmdeploy.yaml                 |
| Ollama            | Default LLM hosting (simple setup)                 | POST /api/generate, GET /api/tags       | /openapi/ollama.yaml                   |
| Opencode Gateway  | Core agent framework (opencode.ai), LLM proxy, metrics, mTLS, mesh | POST /agent, GET /metrics               | /openapi/opencode-gateway.yaml         |
| ZeroClaw          | Agent framework, routing, load balancing, mesh integration (Linkerd) | POST /route, GET /routes                | /openapi/zeroclaw.yaml                 |
| n8n               | Event-driven automation, workflow orchestration    | POST /webhook, UI on :5678              | /openapi/n8n.yaml                      |
| Kafka             | Event streaming, pub/sub backbone                  | Broker on :9092, topics for events      | /openapi/kafka.yaml                    |
| Prometheus        | Metrics scraping, time-series DB                   | GET /metrics, UI on :9090               | /openapi/prometheus.yaml               |
| Grafana           | Dashboards, visualization                          | UI on :3000, import dashboard JSON      | /openapi/grafana.yaml                  |
| Jupyter           | Notebooks, data science, code execution            | UI on :8888, /api/contents, /api/sessions| /openapi/jupyter.yaml                  |
| Learning Agent    | Personalized learning, guidance, feedback          | GET /learning/suggestions, POST /learning/feedback | /openapi/learning.yaml                 |

## How It Ties Together & API Standardization
- **Resident Mentor Agents (AI Instructors):** The core of the Academy. These agents observe your actions, understand the architecture, and proactively guide you to higher skill levels. They are always present, adapting to your goals and teaching you how to use AI by showing you how to use the lab itself.
- **Opencode Agents** (LangChain, custom): Expose APIs via Opencode Gateway, interact with LLMs, emit events to Kafka, expose metrics for Prometheus, and integrate with the mentor system. **All APIs must be documented with OpenAPI for discoverability and integration.**
- **n8n:** Listens to Kafka, triggers workflows, can call Opencode or LMDeploy, automates lab tasks, and supports learning workflows.
- **ZeroClaw:** Agent framework for routing and load balancing, integrates with Linkerd mesh for observability and security.
- **Kafka:** Central event bus for all services (agent events, workflow triggers, logs).
- **Prometheus & Grafana:** Scrape and visualize metrics from all services, including token usage, latency, throughput, agent activity, routing, and mesh traffic. Prometheus scrapes Linkerd proxy stats.
- **Jupyter:** Used for data science, prototyping, and as a UI endpoint. Both Open Notebook and JupyterLab are supported for flexible workflows.

## Example: Level-Up Workflow & API Discovery
1. User interacts with the lab (submits a prompt, runs a workflow, or explores a dashboard).
2. The resident mentor agent observes, understands context, and offers guidance or suggestions to help the user progress.
3. Opencode Gateway authenticates (mTLS/Linkerd mesh), forwards to LMDeploy or other services as needed.
4. All actions, metrics, traces, and API calls are logged and visualized for learning and improvement.
5. n8n and other automation tools can trigger further workflows or learning modules.
6. Metrics, traces, and API endpoints are visualized in Grafana, with the mentor agent highlighting learning opportunities.
7. All APIs are discoverable via their OpenAPI specs, enabling seamless integration and automation.

---

*Update this inventory as new services, integrations, or APIs are added. All new APIs must provide an OpenAPI spec. The Nucleus Academy’s core value is the AI-powered learning experience—autoresearch and simulated spend are value-add, but the resident mentor agent is the differentiator.*
# Observability Inventory & Mapping (gentoofoo.com)

- Ollama (default LLM hosting, simple setup)
- LMDeploy (optional, advanced LLM hosting for performance)
- Grafana (planned at grafana.gentoofoo.com)
- Prometheus (to be deployed)
- Loki (to be deployed)
- Tempo/Jaeger (to be deployed)
- OpenTelemetry Collector (required for traces/metrics)
- Opencode Gateway (FastAPI, see opencode-gateway/)
- ZeroClaw (planned)
- Kafka (planned)
- Traefik/Nginx (reverse proxy, planned)

## Agents
- IDE Agents (see ide-agents/)
- Opencode-powered agents (planned)

## Models
- LMDeploy models (to be specified)

## Workflow Software
- VS Code Remote WSL (integration planned)
- CI/CD (not specified)

## Ingress/Gateways
- Traefik/Nginx (planned)
- Linkerd (required for service mesh, replaces Istio/Envoy)

## Namespaces (Kubernetes, planned)
- observability
- opencode
- lmdeploy
- linkerd-system
- kafka

---

*Update this file as new services, agents, or containers are added or discovered. Ollama is the default LLM hosting option for simplicity and quick setup. LMDeploy is available as a secondary, advanced option for users who want higher performance and are comfortable compiling and configuring it. All new services must use the OpenTelemetry SDK for W3C header propagation and correlated spans to Grafana (Tempo/Jaeger). Tracing is a key requirement; OpenTelemetry must be used with W3C native format. OpenTelemetry collectors must send data to Prometheus and Tempo/Jaeger. Linkerd is the required service mesh (no Istio). Remove all references to Istio.*
