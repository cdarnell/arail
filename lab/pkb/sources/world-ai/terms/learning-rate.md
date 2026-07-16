---
title: "Learning Rate"
tags: [world-ai, training]
aliases: [learning-rate, LR, step size]
---

How big a step the optimizer takes down the gradient — the most consequential training hyperparameter.

The learning rate scales each weight update. Too high and training diverges or oscillates; too low and it crawls or sticks in poor regions. It is usually warmed up, then decayed (e.g. cosine) over training. Picking and scheduling it well is often the difference between a model that converges and one that doesn't.

**Example:** A run that explodes to NaN loss usually just needs a lower peak learning rate or longer warmup.

## Related

- [[warmup]]
- [[cosine-schedule]]
- [[adamw]]
- [[gradient]]
- [[weight-decay]]

Source: authored
