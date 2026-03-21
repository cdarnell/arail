# The Nucleus Lab (Linkerd Edition)
# Project Schoolhouse — IDE Agents Reference

## Executive Summary
The Nucleus Lab (aka Project Schoolhouse) is a "Lab-in-a-Box" for AI learning and experimentation, designed for high-efficiency local deployment. Its core value is the presence of AI instructors—resident mentor agents—that run inside the lab as peer microservices. These agents provide contextual guidance, workflow suggestions, and hands-on learning that help users "level up." Autoresearch and simulated spend are value-add features, but the resident mentor agent is the primary differentiator.

## Plan for Opencode-Powered IDE Agents
- Mesh Integration: All IDE agents must be instrumented with the OpenTelemetry SDK (W3C header propagation) and run inside the Linkerd service mesh. This guarantees mTLS-secured traffic and consistent propagation of trace context.
- True Observability: All agent actions must produce correlated tracing spans. Spans should be visible in Tempo/Jaeger and surfaced in Grafana dashboards so you can trace a user request from the IDE, through the mentor agent, to the LLM backend (`LMDeploy`).
- Resident Mentors: IDE agents are part of the resident mentor system—they should be able to inspect project context and provide contextual, actionable guidance rather than generic API responses.

## Why Run Inside WSL / Ubuntu?
- Peer networking and low-latency access to infrastructure components (Kafka, LMDeploy, Linkerd mesh) when agents run alongside the stack in the same WSL/K3s environment.
- Security & Integration: Running in the same host/mesh enables automatic mTLS, simpler filesystem access for contextual operations, and more realistic testing of mesh behavior.

## Integration with VS Code Remote WSL
- Agents are exposed via the Opencode Gateway and accessible when using VS Code Remote WSL. The IDE is effectively "projected" into the environment where the agent runs, enabling agents to operate as local co-processes that can read workspace files and interact with the user session.
- TODO: Define exact access patterns and any authentication plumbing required for Remote WSL -> Opencode Gateway calls.

## Metrics and Token Usage
- Agents must expose `/metrics` for Prometheus scraping. Track token usage per-call and per-session so operational cost and usage patterns are visible in Grafana.
- TODO: Decide on labels/metrics schema for token accounting and session correlation.

## Interaction with LMDeploy
- Agents should call `LMDeploy` using internal mesh addresses (for example `http://lmdeploy.local:8000`) so that LLM calls are part of the global trace and benefit from Linkerd load balancing and retries.
- TODO: Document request/response patterns, error handling, and backoff/retry strategies for LMDeploy calls.

## Example Commands & Workflows
- Call LMDeploy from an agent:
```bash
curl -X POST http://lmdeploy.local:8000/generate -d '{"prompt": "Test"}'
```
- Check agent metrics:
```bash
curl http://opencode.local:9100/metrics
```
- Test DNS inside WSL:
```bash
ping opencode.local
```

## Notes
- Replace TODOs with implementation details as the agent features are built. All new agents must use OpenTelemetry with W3C header propagation and publish correlated spans. Linkerd is the required mesh for production-like behavior in the Nucleus Lab.

-- End of combined reference
