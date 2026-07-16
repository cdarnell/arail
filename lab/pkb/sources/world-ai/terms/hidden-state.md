---
title: "Hidden State"
tags: [world-ai, fundamentals]
aliases: [hidden-state, activations, representations]
---

The vector a model holds for each token at each layer — its evolving internal representation.

A hidden state is the intermediate activation vector for a token at a given layer, carrying the model's current understanding of that token in context. Hidden states are transformed layer by layer; the final layer's states are projected to logits. Probing and interpretability work studies what these vectors encode.

**Example:** By a middle layer, the hidden state for 'bank' already reflects whether the sentence is about rivers or money.

## Related

- [[embeddings]]
- [[logits]]
- [[transformer]]
- [[attention]]

Source: authored
