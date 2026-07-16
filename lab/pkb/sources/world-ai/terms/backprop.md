---
title: "Backprop"
tags: [world-ai, training]
aliases: [backprop, backpropagation, backward pass]
---

The algorithm that computes how to nudge every weight by propagating error gradients backward.

Backpropagation applies the chain rule to compute the gradient of the loss with respect to every parameter, flowing from the output layer back to the input. Those gradients tell the optimizer which direction to move each weight to reduce error.

**Example:** After a forward pass yields loss 2.3, backprop computes the gradient for every weight; AdamW then updates them.

## Related

- [[gradient]]
- [[adamw]]
- [[dropout]]

Source: authored
