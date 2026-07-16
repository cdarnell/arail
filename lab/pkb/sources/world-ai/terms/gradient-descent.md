---
title: "Gradient Descent"
tags: [world-ai, fundamentals]
aliases: [gradient-descent]
---

The core optimization: repeatedly step parameters in the direction that most reduces the loss.

Gradient descent computes the gradient of the loss with respect to the parameters and nudges them in the opposite (downhill) direction, iterating until the loss is low. Variants (SGD, AdamW) differ in how they estimate and scale that step. It is how essentially all deep models are trained.

**Example:** Each step, the optimizer moves weights a little downhill on the loss surface toward a minimum.

## Related

- [[sgd]]
- [[adamw]]
- [[gradient]]
- [[backprop]]
- [[loss-function]]
- [[learning-rate]]

Source: authored
