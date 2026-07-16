---
title: "Knowledge Base"
tags: [world-ai, architecture]
aliases: [knowledge-base, KB]
---

An external, queryable store of facts and documents a model retrieves from instead of relying on weights alone.

A knowledge base is the curated, updatable corpus a retrieval system draws on — documents, facts, or embeddings indexed for search. It is the external memory that makes RAG work: keeping knowledge outside the model means it can be updated, cited, and audited without retraining. In CoALA terms it backs the agent's semantic memory.

**Example:** A support bot retrieves the current refund policy from its knowledge base, so updating one document changes every answer instantly.

## Related

- [[rag]]
- [[semantic-memory]]
- [[embeddings]]
- [[long-term-memory]]
- [[provenance]]

Source: authored
