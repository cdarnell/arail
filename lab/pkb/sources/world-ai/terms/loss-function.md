---
title: "Loss Function"
tags: [world-ai, training]
aliases: [loss-function, objective, cost function]
---

The scalar that measures how wrong a model's predictions are — what training minimizes.

The loss function turns a batch of predictions and targets into a single number quantifying error; training adjusts weights to reduce it via gradient descent. For language models it is almost always cross-entropy over next-token predictions. The choice of loss defines what 'good' means to the optimizer.

**Example:** Cross-entropy loss is high when the model assigns low probability to the actual next token, pushing gradients to raise it.

## Related

- [[cross-entropy]]
- [[gradient]]
- [[backprop]]
- [[adamw]]
- [[perplexity]]

Source: authored
