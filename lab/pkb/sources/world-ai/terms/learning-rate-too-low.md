---
title: "Learning rate too low"
tags: [world-ai, conditions]
aliases: [learning-rate-too-low]
---

LR is so small that the optimizer barely moves — training stalls.

When the learning rate is too low, gradient updates are so small that the model barely changes per step. The loss either plateaus prematurely or converges too slowly to be useful within the compute budget. Often set accidentally when copying a LR from a much larger batch-size run without rescaling, or when a cosine schedule decays to near-zero too quickly.

**Example:** A run with LR 1e-6 on a fresh init shows loss barely improving after 5k steps; raising to 1e-4 restores normal descent.

## Related

- [[learning-rate]]
- [[loss-plateau]]
- [[slow-convergence]]
- [[switch-optimizer]]

Source: HF Trainer docs; Goodfellow et al. — Deep Learning ch.8 (hyperparameter tuning)
