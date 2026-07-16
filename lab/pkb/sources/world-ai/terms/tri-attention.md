---
title: "Tri-Attention"
tags: [world-ai, architecture]
aliases: [tri-attention, three-way attention, explicit context interaction]
---

Attention that adds an explicit third 'context' term to the usual query-key interaction, modeling three-way relationships instead of pairwise ones.

Standard ('bi-') attention scores pairs: a query against keys. Tri-Attention introduces a third element — typically an explicit context representation — so relevance is computed over (query, key, context) triplets rather than (query, key) pairs. By making the context a first-class factor in the score (e.g. via a tensor/trilinear interaction) it captures dependencies that pairwise attention folds away, which helps retrieval-augmented and context-conditioned models reason about how a query and a candidate relate *given* the surrounding context.

**Example:** Ranking a retrieved passage for a question, tri-attention scores question x passage x conversation-context jointly, so a passage that only matters given the prior turn is surfaced.

## Related

- [[attention]]
- [[multi-head-attention]]
- [[cross-attention]]
- [[rag]]

Source: authored
