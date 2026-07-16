---
title: "Learning rate too high"
tags: [world-ai, conditions]
aliases: [learning-rate-too-high]
---

Peak LR exceeds what the schedule/optimizer can stabilize.

A peak learning rate too large for the warmup length and batch size drives parameter updates past the stable basin, producing divergence or oscillation. The relationship between LR and batch size is roughly linear (linear scaling rule): larger batches tolerate larger LRs. A 1B+ parameter model with a 100-step warmup is especially sensitive because the model is not yet pre-conditioned. The fix is to reduce the peak LR and/or lengthen the warmup.

**Example:** Peak LR 5e-4 with a 100-step warmup on a 1B model diverges; 1e-4 with a 500-step warmup converges.

## Related

- [[learning-rate]]
- [[warmup]]
- [[reduce-learning-rate]]
- [[apply-warmup-schedule]]
- [[diverging-loss]]
- [[oscillating-loss]]

Source: HF Trainer docs (lr_scheduler_type, warmup_steps); Goodfellow et al. ch.8; OLMo logbook
