---
title: "Cosine Schedule"
tags: [world-ai, training]
aliases: [cosine-schedule, cosine decay]
---

Decay the learning rate along a cosine curve from its peak down toward zero over training.

A cosine learning-rate schedule ramps up during warmup, then decays the rate following a half-cosine from peak to a small final value. The smooth, front-loaded-then-gentle decay tends to train stably and finish in a good minimum; it is a default for large pretraining runs.

**Example:** Over 100k steps the LR warms up for 2k steps, then eases down a cosine curve to near zero by the end.

## Related

- [[learning-rate]]
- [[warmup]]
- [[adamw]]
- [[pretraining]]

Source: authored
