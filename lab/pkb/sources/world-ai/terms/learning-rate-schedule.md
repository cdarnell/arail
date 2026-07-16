---
title: "Learning rate schedule"
tags: [world-ai, training]
aliases: [learning-rate-schedule]
---

A plan for how the learning rate changes over the course of training.

Rather than using a fixed LR, schedules vary the rate over time. Common schedules: linear warmup + linear decay; cosine annealing (LR follows a cosine curve to a near-zero minimum); step decay (multiplies LR by a factor every N steps); constant (no decay, only warmup). The HF Trainer supports these via `lr_scheduler_type`. The schedule interacts with the optimizer and batch size; getting it wrong causes plateaus or oscillation.

**Example:** Setting `lr_scheduler_type='cosine'` with `warmup_ratio=0.05` applies a 5% warmup followed by cosine decay — the standard regime for instruction tuning.

## Related

- [[learning-rate]]
- [[warmup]]
- [[loss-plateau]]
- [[apply-warmup-schedule]]

Source: HF Trainer docs (lr_scheduler_type, warmup_ratio); Goodfellow et al. — Deep Learning ch.8; NVIDIA training guide
