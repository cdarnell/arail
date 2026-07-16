---
title: "Batch normalization"
tags: [world-ai, architecture]
aliases: [batch-normalization]
---

Normalizes activations across the batch dimension to stabilize training.

Batch normalization (Ioffe & Szegedy, 2015) normalizes activations across the mini-batch, then applies learned scale and shift parameters. It reduces the sensitivity to initialization and allows higher learning rates. Standard in CNNs and MLPs; replaced by layer normalization in transformer models. At inference, batch statistics are replaced by running estimates accumulated during training.

**Example:** Adding batch normalization after each convolutional layer in a CNN allows training with LR 10× higher than without, significantly accelerating convergence.

## Related

- [[layer-normalization]]
- [[internal-covariate-shift]]

Source: Ioffe & Szegedy — Batch Normalization arXiv:1502.03167; Goodfellow et al. — Deep Learning ch.8
