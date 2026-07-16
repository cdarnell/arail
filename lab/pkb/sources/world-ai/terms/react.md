---
title: "ReAct"
tags: [world-ai, architecture]
aliases: [react, reason + act]
---

An agent pattern that interleaves reasoning steps ('thoughts') with actions ('tool calls') in a loop.

ReAct prompts a model to alternate between reasoning traces and concrete actions: think, act (call a tool or query the environment), observe the result, think again. Interleaving reasoning with grounded actions lets the agent plan, gather information, and correct course mid-task — the backbone pattern of most tool-using agents.

**Example:** Thought: 'I need the population'; Action: search('Tokyo population'); Observation: '14M'; Thought: 'now compute the ratio'.

## Related

- [[agent]]
- [[agentic]]
- [[tool-use]]
- [[chain-of-thought]]
- [[reflexion]]
- [[coala]]

Source: authored
