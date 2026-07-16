---
title: "Grounding"
tags: [world-ai, architecture]
aliases: [grounding]
---

Connecting an agent's language to the real world via tools, environments, or retrieved facts.

Grounding is how a language agent's words map onto reality: executing tools, observing an environment, or anchoring claims to retrieved sources. In CoALA, grounding actions are the external actions that affect or read the outside world, as opposed to internal reasoning. Ungrounded agents hallucinate; grounded ones can verify.

**Example:** Instead of guessing a file's contents, the agent grounds by actually reading the file and reasoning over the real bytes.

## Related

- [[coala]]
- [[tool-use]]
- [[rag]]
- [[hallucination]]
- [[agent]]

Source: authored
