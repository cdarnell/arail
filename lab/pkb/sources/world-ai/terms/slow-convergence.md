---
title: "Slow convergence"
tags: [world-ai, symptoms]
aliases: [slow-convergence]
---

Loss decreases, but far more slowly than expected for the compute budget.

Slow convergence is when the training loss improves, but the descent rate is so low that the run will not reach the target loss within its compute budget. Root causes include a learning rate that is too low, a poor optimizer choice, a cold-start (insufficient warmup), or inadequate data quality. Distinguished from a plateau by the fact that improvement is still occurring — just too slowly.

**Example:** After 10k steps (half the compute budget), loss is at 3.1 instead of the expected 2.5, indicating the run will miss the target without an intervention.

## Related

- [[learning-rate-too-low]]
- [[loss-plateau]]
- [[apply-warmup-schedule]]
- [[switch-optimizer]]

Source: Goodfellow et al. — Deep Learning ch.8; HF Trainer docs; OLMo training logbook
