---
title: "Adam optimizer"
tags: [world-ai, training]
aliases: [adam-optimizer]
---

Adaptive moment estimation — per-parameter adaptive LR via running mean and variance of gradients.

Adam (Kingma & Ba, 2015) maintains exponential moving averages of both the gradient (first moment, m) and the squared gradient (second moment, v) for each parameter. The adaptive per-parameter LR means that parameters with sparse or noisy gradients still receive meaningful updates. Adam is the default optimizer for most deep learning; AdamW is preferred for transformer fine-tuning (decoupled weight decay).

**Example:** Adam with lr=1e-3, beta1=0.9, beta2=0.999 is the default in many frameworks; it adapts per-parameter effective LR based on historical gradient magnitudes.

## Related

- [[adamw]]
- [[switch-optimizer]]
- [[learning-rate]]

Source: Kingma & Ba — Adam arXiv:1412.6980; Goodfellow et al. — Deep Learning §8.5; PyTorch Adam docs
