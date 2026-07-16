---
title: "ReLU"
tags: [world-ai, architecture]
aliases: [relu]
---

Rectified Linear Unit — max(0, x). The most common hidden-layer activation.

ReLU (Rectified Linear Unit) applies max(0, x) element-wise, outputting zero for negative inputs and the input itself for positive inputs. It is computationally cheap and empirically effective for many architectures. Its main failure mode is 'dead neurons' — units that always receive negative input and therefore always output zero, ceasing to learn. GELU has largely replaced ReLU in transformer feed-forward layers.

**Example:** In a standard MLP layer, ReLU(Wx + b) clips negative pre-activations to zero, introducing non-linearity without saturation for positive values.

## Related

- [[gelu]]
- [[dead-neurons]]
- [[transformer]]

Source: Goodfellow et al. — Deep Learning §6.3.1; PyTorch ReLU docs
