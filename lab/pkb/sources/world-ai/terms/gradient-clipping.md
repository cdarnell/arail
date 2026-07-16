---
title: "Gradient Clipping"
tags: [world-ai, training]
aliases: [gradient-clipping]
---

Cap the gradient's magnitude each step to prevent exploding updates from destabilizing training.

Gradient clipping rescales the gradient when its norm exceeds a threshold, so a rare huge gradient can't blow up the weights. It is standard insurance for transformer training, where occasional spikes (from hard batches or numerical issues) would otherwise cause loss to diverge.

**Example:** Clipping the global gradient norm to 1.0 turns a run that periodically NaNs into a stable one.

## Related

- [[gradient]]
- [[backprop]]
- [[learning-rate]]
- [[loss-function]]

Source: authored
