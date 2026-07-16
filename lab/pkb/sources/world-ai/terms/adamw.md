---
title: "AdamW"
tags: [world-ai, training]
aliases: [adamw, Adam with weight decay]
---

The default optimizer for training transformers — Adam with decoupled weight decay.

AdamW adapts the learning rate per parameter using running estimates of gradient mean and variance, and decouples weight decay from the gradient update for cleaner regularization. It is the workhorse optimizer for LLM training.

**Example:** A typical run: AdamW with lr=2e-4, betas=(0.9, 0.95), weight_decay=0.1, plus warmup and a cosine schedule.

## Related

- [[gradient]]
- [[backprop]]
- [[warmup]]

Source: authored
