---
title: "Softmax"
tags: [world-ai, fundamentals]
aliases: [softmax, softmax function]
---

Turns a vector of logits into a probability distribution that sums to 1.

Softmax exponentiates each logit and divides by the sum, producing positive values that add to 1 — a probability distribution. It picks the next token from logits and, inside attention, weights how much each token attends to others.

**Example:** Logits [2.0, 1.0, 0.1] become probabilities about [0.66, 0.24, 0.10] after softmax.

## Related

- [[logits]]
- [[attention]]
- [[temperature]]

Source: authored
