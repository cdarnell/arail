---
title: "Reflexion"
tags: [world-ai, architecture]
aliases: [reflexion]
---

An agent loop that converts failure feedback into written self-reflection stored in memory for the next attempt.

Reflexion is an agent method where, after a failed attempt, the agent generates a verbal self-reflection on what went wrong and stores it in episodic memory. On the next attempt that reflection is added to the context, so the agent improves over trials without updating any weights — reinforcement via language, not gradients.

**Example:** A coding agent fails a test, writes 'I forgot to handle the empty-list case', and on the next try uses that note to pass.

## Related

- [[reflection]]
- [[react]]
- [[episodic-memory]]
- [[agent]]

Source: authored
