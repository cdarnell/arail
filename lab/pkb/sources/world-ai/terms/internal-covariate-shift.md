---
title: "Internal covariate shift"
tags: [world-ai, conditions]
aliases: [internal-covariate-shift]
---

Distribution of layer activations shifts during training, slowing convergence.

As the weights of earlier layers change during training, the distribution of inputs to later layers shifts continuously, forcing later layers to constantly re-adapt. This was the original motivation for batch normalization (Ioffe & Szegedy, 2015). In practice, the term is used loosely to describe unstable activation distributions that slow convergence. Layer normalization addresses a similar problem for sequence models.

**Example:** A 10-layer MLP without normalization converges in 50k steps; adding batch normalization achieves the same loss in 20k steps by stabilizing intermediate activations.

## Related

- [[vanishing-gradients]]
- [[batch-normalization]]
- [[layer-normalization]]
- [[slow-convergence]]

Source: Ioffe & Szegedy — Batch Normalization arXiv:1502.03167; Goodfellow et al. — Deep Learning §8.7
