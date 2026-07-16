---
title: "Logits"
tags: [world-ai, fundamentals]
aliases: [logits, logit]
---

The model's raw, unnormalized output scores over the vocabulary, before softmax makes them probabilities.

Logits are the final layer's raw scores — one per vocabulary token — not yet normalized into probabilities. Sampling controls (temperature, top-k/p) operate on logits before softmax converts them into the next-token distribution.

**Example:** Dividing logits by a temperature of 0.2 sharpens them, making the top token far more likely after softmax.

## Related

- [[softmax]]
- [[temperature]]
- [[beam-search]]

Source: authored
