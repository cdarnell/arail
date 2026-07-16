---
title: "Semantic Memory"
tags: [world-ai, architecture]
aliases: [semantic-memory]
---

An agent's store of general world knowledge and facts, decoupled from any single experience.

Semantic memory holds the agent's general, context-free knowledge — facts, concepts, and learned domain knowledge — as opposed to specific episodes. In language agents it spans the model's parametric knowledge plus an external knowledge base (often a vector store) the agent reads from and writes distilled facts to.

**Example:** The agent's vector store holds 'the company's refund window is 30 days' — a fact, not tied to when it was learned, retrieved whenever refunds come up.

## Related

- [[coala]]
- [[episodic-memory]]
- [[rag]]
- [[embeddings]]
- [[long-term-memory]]

Source: authored
