---
title: "Cross-Entropy"
tags: [world-ai, training]
aliases: [cross-entropy, cross-entropy loss]
---

The standard LM loss: penalize the model by the negative log-probability it gave the correct token.

Cross-entropy measures the gap between the model's predicted distribution and the true distribution (a one-hot target for the actual next token). Minimizing it maximizes the log-likelihood of the data; exponentiating the mean cross-entropy gives perplexity. It is the workhorse loss for next-token prediction.

**Example:** If the model gave the right next word a 0.5 probability, its cross-entropy there is -log(0.5) ~ 0.69 nats.

## Related

- [[loss-function]]
- [[perplexity]]
- [[softmax]]
- [[logits]]

Source: authored
