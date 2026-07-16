---
title: "SGD"
tags: [world-ai, fundamentals]
aliases: [sgd, stochastic gradient descent]
---

Stochastic gradient descent: estimate the gradient from a small random batch instead of the whole dataset.

Stochastic gradient descent approximates the true gradient using one mini-batch at a time, making each step cheap and adding noise that can help escape poor minima. Modern training uses momentum and adaptive variants (AdamW) built on this idea.

**Example:** Rather than read all 10M examples per step, SGD updates weights from a 32-example batch.

## Related

- [[gradient-descent]]
- [[adamw]]
- [[batch-size]]
- [[gradient]]

Source: authored
