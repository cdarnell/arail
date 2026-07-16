---
title: "Weight initialization"
tags: [world-ai, training]
aliases: [weight-initialization]
---

How weights are set before training — a critical determinant of early convergence.

Poor weight initialization causes vanishing or exploding gradients before training even begins. Key insight: variance of activations should stay roughly constant across layers. He initialization (for ReLU) and Xavier/Glorot initialization (for tanh/sigmoid) are designed to achieve this. Modern large language models typically use a small normal distribution with std proportional to 1/√d_model, sometimes with scaled initialization for residual paths.

**Example:** A 20-layer MLP initialized with all weights sampled from N(0, 1) (instead of N(0, 0.02)) produces exploding activations from the first forward pass.

## Related

- [[dead-neurons]]
- [[vanishing-gradients]]
- [[residual-connection]]

Source: He et al. — Delving Deep into Rectifiers arXiv:1502.01852; Glorot & Bengio (2010) — Understanding Difficulty of Training Deep FFNs; Goodfellow et al. — Deep Learning §8.4
