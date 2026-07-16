---
title: "Embeddings"
tags: [world-ai, fundamentals]
aliases: [embeddings, embedding vectors]
---

Dense numeric vectors representing tokens or text so similar meanings sit close together.

An embedding maps a token or piece of text to a vector in high-dimensional space where geometric closeness reflects semantic similarity. Models learn input embeddings for tokens; separate embedding models turn whole documents into vectors for search and RAG.

**Example:** 'king' minus 'man' plus 'woman' lands near 'queen'; RAG retrieves the docs whose embeddings are nearest the query's.

## Related

- [[tokenizer]]
- [[transformer]]
- [[attention]]

Source: authored
