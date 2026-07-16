---
title: "Scaling Laws"
tags: [world-ai, training]
aliases: [scaling-laws, neural scaling laws]
---

Empirical power-law curves showing model loss falls predictably as parameters, data, and compute grow.

Scaling laws are power-law relationships found empirically: a model's loss drops smoothly and predictably as parameters, training tokens, and compute increase together. They let labs forecast a model's capability before training it, and they later motivated training smaller models on far more data (compute-optimal, Chinchilla-style).

**Example:** Scaling laws predicted how much a 10x larger compute budget would cut loss, so a lab could plan a frontier run's size and data in advance.

## Related

- [[benchmark]]
- [[distillation]]
- [[perplexity]]

Source: authored
