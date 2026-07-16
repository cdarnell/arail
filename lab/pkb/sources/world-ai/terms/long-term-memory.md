---
title: "Long-Term Memory"
tags: [world-ai, architecture]
aliases: [long-term-memory, persistent memory]
---

An agent's durable store that survives across sessions, beyond the context window.

Long-term memory is any persistent store the agent reads from and writes to across runs — usually an external database or vector index holding episodic and semantic memories. It is the answer to the context window's hard limit: instead of cramming everything into the prompt, the agent retrieves only what's relevant now. Writing, organizing, and forgetting are first-class problems.

**Example:** Across weeks of chats the agent keeps a profile in long-term memory ('user is vegetarian, prefers email') and retrieves it on each new session.

## Related

- [[working-memory]]
- [[episodic-memory]]
- [[semantic-memory]]
- [[rag]]
- [[context-window]]

Source: authored
