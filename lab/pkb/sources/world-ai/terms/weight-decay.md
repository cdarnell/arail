---
title: "Weight Decay"
tags: [world-ai, training]
aliases: [weight-decay, L2 regularization]
---

A penalty that nudges weights toward zero each step, discouraging overly large parameters and overfitting.

Weight decay shrinks parameters by a small factor every update, regularizing the model toward simpler solutions and improving generalization. In AdamW it is applied decoupled from the gradient-based update (the 'W'), which is why AdamW is preferred over plain Adam for transformers.

**Example:** A weight decay of 0.1 keeps weights from drifting large, often improving held-out loss versus none.

## Related

- [[adamw]]
- [[regularization]]
- [[overfitting]]
- [[learning-rate]]

Source: authored
