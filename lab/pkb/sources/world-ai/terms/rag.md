---
title: "RAG"
tags: [world-ai, architecture]
aliases: [rag, Retrieval-Augmented Generation]
---

Fetch relevant documents at query time and feed them to the model as context.

RAG retrieves passages from a knowledge store and injects them into the prompt, so the model answers from fresh, specific data rather than memory. It's the opposite of distillation — knowledge stays external and looked-up.

**Example:** A support bot retrieves the latest policy doc and answers from it, with no retraining when the policy changes.

## Related

- [[raft]]
- [[context-window]]
- [[knowledge-base]]

Source: QuKaiZen AI Dictionary
