---
title: "EMA"
tags: [world-ai, training]
aliases: [ema, exponential moving average]
---

Exponential moving average of weights kept alongside training for a smoother, often better, final model.

An exponential moving average maintains a slowly-updated running average of the model's weights during training; the averaged weights are frequently more stable and generalize better than the raw final ones. It is cheap insurance widely used in large training runs.

**Example:** Evaluating the EMA weights instead of the last step's weights often yields a slightly better model.

## Related

- [[checkpoint]]
- [[generalization]]
- [[sgd]]

Source: authored
