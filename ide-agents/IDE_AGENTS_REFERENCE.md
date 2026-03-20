
# The Nucleus Academy (Linkerd Edition)
# Project Schoolhouse — IDE Agents Reference

## Executive Summary
The Nucleus Academy is a "Lab-in-a-Box" for AI learning and experimentation, designed for high-efficiency local deployment. Its core value is the presence of AI instructors—resident mentor agents—who help you LEVEL UP by providing contextual guidance, workflow suggestions, and hands-on learning. Autoresearch and simulated spend are value-add features, but the real differentiator is the Academy’s focus on continuous skill development and AI-powered mentorship.


## Plan for Opencode-Powered IDE Agents
- All IDE agents must be instrumented with the OpenTelemetry SDK (W3C header propagation) and run in the Linkerd mesh for secure, observable traffic. Tracing is a key requirement; all spans must be correlated and visible in Grafana (Tempo/Jaeger).
- IDE agents are part of the resident mentor system, providing contextual guidance and helping users level up as they work in the lab.

## Why Run Inside WSL Ubuntu?
- Mesh networking, mTLS (via Linkerd), Kafka, LMDeploy access
- **TODO:** Expand on security and integration benefits.

## Integration with VS Code Remote WSL
- **TODO:** How agents will be accessible from VS Code Remote WSL.

## Metrics and Token Usage
- **TODO:** How agents will expose metrics and track token usage.

## Interaction with LMDeploy
- **TODO:** How agents will call LMDeploy and handle responses.

## Example Commands & Workflows
- **Call LMDeploy from agent:**
  ```bash
  curl -X POST http://lmdeploy.local:8000/generate -d '{"prompt": "Test"}'
  ```
- **Check agent metrics:**
  ```bash
  curl http://opencode.local:9100/metrics
  ```
- **Test DNS inside WSL:**
  ```bash
  ping opencode.local
  ```

*Replace TODOs with actual steps as you implement each part. All new agents must use the OpenTelemetry SDK for W3C header propagation and correlated spans to Grafana (Tempo/Jaeger). Linkerd is the required service mesh. The Nucleus Academy’s core value is the AI-powered learning experience—autoresearch and simulated spend are value-add, but the resident mentor agent is the differentiator.*
