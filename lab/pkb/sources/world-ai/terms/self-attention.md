---
title: "Self-attention"
tags: [world-ai, architecture]
aliases: [self-attention]
---

Each token attends to all other tokens in the sequence to build context-aware representations.

Self-attention computes a weighted sum of value vectors, where weights are derived from the compatibility (dot-product) of query and key vectors for each token pair. It allows every position to directly attend to every other position, capturing long-range dependencies without the vanishing-gradient path lengths of RNNs. Scaled by 1/√d_k to prevent large dot products.

**Example:** In a decoder-only transformer, causal (masked) self-attention ensures each token can only attend to past tokens during generation.

## Related

- [[transformer]]
- [[multi-head-attention]]
- [[positional-encoding]]

Source: Vaswani et al. — Attention Is All You Need arXiv:1706.03762
