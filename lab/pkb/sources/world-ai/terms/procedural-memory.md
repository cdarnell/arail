---
title: "Procedural Memory"
tags: [world-ai, architecture]
aliases: [procedural-memory, skill memory]
---

An agent's memory of how to do things — its skills, routines, and the agent code itself.

Procedural memory is knowledge of *how* to act: learned skills, reusable routines, and in CoALA the agent's own implementation (its prompts, tools, and decision logic). Some of it is implicit in the model's weights; some is explicit, editable code or saved skills the agent can extend over time. It is the 'muscle memory' versus episodic/semantic's 'facts'.

**Example:** Having solved a class of tasks, the agent writes a reusable 'extract-invoice-fields' skill to procedural memory and calls it directly next time.

## Related

- [[coala]]
- [[episodic-memory]]
- [[semantic-memory]]
- [[tool-use]]
- [[agent]]

Source: authored
