# The Nucleus Academy (Linkerd Edition)
    # Project Schoolhouse — IDE Agents Reference
    
    ## Executive Summary
    The Nucleus Academy is a "Lab-in-a-Box" for AI learning and experimentation, designed for high-efficiency local deployment. Its core value is the presence of AI instructors—**Resident Mentor Agents**—who live within the lab as peer microservices. These agents provide contextual guidance, workflow suggestions, and hands-on learning, turning a standard VM into a guided "Schoolhouse" environment.
    
    ## Plan for Opencode-Powered IDE Agents
    * **Mesh Integration:** All IDE agents are instrumented with the **OpenTelemetry SDK (W3C header propagation)** and run within the **Linkerd mesh**. This ensures all traffic is secured via mTLS and fully observable.
    * **True Observability:** Every agent action is correlated via tracing. Spans are visible in Grafana (Tempo/Jaeger), allowing you to trace a user request from the IDE, through the mentor agent, to the LLM backend (`LMDeploy`).
    
    ## Why Run Inside WSL Ubuntu?
    * **Peer Networking:** By running inside the same WSL/K3s environment as your stack, agents have direct, low-latency access to **Kafka**, **LMDeploy**, and the mesh.
    * **Security & Integration:** Agents leverage the mesh's mTLS automatically. Because they run on the same host, they share the project's filesystem context, allowing them to act as true "resident" mentors rather than external APIs.
    
    ## Integration with VS Code Remote WSL
    * **Local Co-Process:** Agents are accessible via the **Opencode Gateway**. When using VS Code Remote WSL, the IDE is "projected" into the environment where the agent lives. This creates a "Direct Integration" feel where the agent can interact with the workspace as a local peer.
    
    ## Metrics and Token Usage
    * **Standardized Stamping:** Agents expose metrics via a `/metrics` endpoint. They track token usage per-call and per-session, which is then scraped by **Prometheus** and visualized in **Grafana**. This allows for "True Observability" of the AI's operational costs and performance.
    
    ## Interaction with LMDeploy
    * **Mesh-Native Calls:** Agents call `LMDeploy` using the internal mesh address `http://lmdeploy.local:8000`. This ensures that every LLM interaction is part of the global trace and benefits from Linkerd's load balancing and reliability features.
    
    ## Example Commands & Workflows
    * **Call LMDeploy from agent:** `curl -X POST http://lmdeploy.local:8000/generate -d ' {"prompt": "Test"} '`
    * **Check agent metrics:** `curl http://opencode.local:9100/metrics`
    * **Test DNS inside WSL:** `ping opencode.local`
    
