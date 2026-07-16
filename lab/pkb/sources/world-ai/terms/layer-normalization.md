---
title: "Layer normalization"
tags: [world-ai, architecture]
aliases: [layer-normalization]
---

Normalizes activations across the feature dimension within each example.

Layer normalization (Ba et al., 2016) normalizes activations across the feature dimension (not the batch dimension), computing mean and variance per-example, per-layer. This makes it suitable for sequence models where batch normalization is inapplicable (variable-length sequences, small batch sizes). Standard in all transformer architectures. Applied before or after each sub-layer (Pre-LN vs Post-LN, with Pre-LN being more stable for deep models).

**Example:** In GPT-2 (Pre-LN), LayerNorm is applied to the residual stream before both the self-attention and the MLP sub-layers.

## Related

- [[transformer]]
- [[batch-normalization]]
- [[vanishing-gradients]]
- [[internal-covariate-shift]]

Source: Ba et al. — Layer Normalization arXiv:1607.06450; Goodfellow et al. — Deep Learning ch.8
