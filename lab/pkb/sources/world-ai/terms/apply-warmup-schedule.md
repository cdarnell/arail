---
title: "Apply warmup schedule"
tags: [world-ai, care-actions]
aliases: [apply-warmup-schedule]
---

Ramp the LR from near-zero to peak over N steps before the main schedule.

Starting training with the full learning rate before the optimizer has accumulated good gradient statistics can cause early divergence. A warmup phase ramps the LR linearly from near-zero to the peak LR over a fixed number of steps (commonly 1–5% of total steps, or 500–2000 steps for large models), giving the model time to settle before the optimizer takes large steps. After warmup, a cosine or linear decay schedule is applied.

**Example:** Adding a 500-step linear warmup before the cosine schedule on a 1B model eliminates the early-step divergence that occurred with no warmup.

## Related

- [[learning-rate-too-high]]
- [[warmup]]
- [[learning-rate-schedule]]
- [[reduce-learning-rate]]

Source: HF Trainer docs (warmup_steps, lr_scheduler_type='cosine_with_restarts'); NVIDIA training guide; OLMo training config
