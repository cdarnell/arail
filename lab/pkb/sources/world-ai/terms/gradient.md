---
title: "Gradient"
tags: [world-ai, training]
aliases: [gradient, gradients]
---

The vector of partial derivatives telling how the loss changes as you tweak each weight.

A gradient points in the direction of steepest increase of the loss; training steps move weights the opposite (descent) way. Gradient magnitude and stability (vanishing/exploding) are central concerns, handled with clipping, normalization, and good optimizers.

**Example:** Gradient clipping caps the global gradient norm (e.g., 1.0) to stop a huge update from blowing up training.

## Related

- [[backprop]]
- [[adamw]]
- [[fsdp]]

Source: authored
