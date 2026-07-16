---
title: "Oscillating loss"
tags: [world-ai, symptoms]
aliases: [oscillating-loss]
---

Loss bounces between high and low values without a clear downward trend.

When the loss oscillates — alternating high and low values — rather than following a smooth descent, the learning rate is typically too large for the batch size or the optimizer is not suited to the curvature. Oscillation differs from noise (random variation around a trend) by having a regular pattern. Reducing the LR or switching to a more adaptive optimizer usually smooths it.

**Example:** Every other logging step, loss alternates between 2.1 and 3.4 without a net decrease over 5k steps — dropping LR by 3× reduces the oscillation to noise-level variation.

## Related

- [[learning-rate-too-high]]
- [[diverging-loss]]
- [[reduce-learning-rate]]
- [[switch-optimizer]]

Source: Goodfellow et al. — Deep Learning ch.8 (learning rate); PyTorch optimizer docs
