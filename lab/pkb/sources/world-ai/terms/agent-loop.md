---
title: "Agent Loop"
tags: [world-ai, architecture]
aliases: [agent-loop, perceive-decide-act loop]
---

The repeating perceive-decide-act cycle that drives an autonomous agent.

An agent loop iterates: observe the environment/state, decide the next action (reason, retrieve, or call a tool), act, then observe the result — repeating until the goal is met or a stop condition fires. It is the control structure underlying ReAct and CoALA's decision procedure.

**Example:** The agent loops: read tool output, think, call the next tool, until the task is complete.

## Related

- [[react]]
- [[coala]]
- [[tool-use]]
- [[planning]]
- [[orchestration]]

Source: authored
