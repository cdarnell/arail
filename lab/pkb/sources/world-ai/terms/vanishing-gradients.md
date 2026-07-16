---
title: "Vanishing gradients"
tags: [world-ai, symptoms]
aliases: [vanishing-gradients]
---

Gradients shrink toward zero in early layers — no useful learning signal.

In deep networks without skip connections or normalization, gradients can shrink exponentially as they are backpropagated, making early-layer weights effectively frozen. The symptom is that early-layer losses barely improve while later layers train. Addressed by architectural choices (residual connections, layer normalization) rather than hyperparameter tuning.

**Example:** In a 20-layer MLP without residual connections, the first five layers show near-zero gradient norms throughout training; adding residual connections equalizes gradient flow.

## Related

- [[dead-neurons]]
- [[internal-covariate-shift]]
- [[slow-convergence]]
- [[layer-normalization]]
- [[residual-connection]]

Source: Goodfellow et al. — Deep Learning §10.7; Karpathy nanoGPT architectural notes
