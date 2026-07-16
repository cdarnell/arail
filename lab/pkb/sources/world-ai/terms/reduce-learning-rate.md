---
title: "Reduce learning rate"
tags: [world-ai, care-actions]
aliases: [reduce-learning-rate]
---

Lower the peak LR (and/or lengthen warmup) to restabilize.

Reduce peak LR by 2–10× and/or extend the warmup period; re-run from the last good checkpoint to confirm loss resumes its downward trend. This is the primary intervention for learning-rate-too-high producing divergence or oscillation. The new LR should be confirmed by observing a stable descent for at least a few thousand steps before committing to the full run.

**Example:** After divergence at LR 5e-4, roll back to the step-3k checkpoint, drop to 1e-4, and extend warmup from 100 to 500 steps; loss descends normally.

## Related

- [[learning-rate-too-high]]
- [[resume-from-checkpoint]]
- [[apply-warmup-schedule]]
- [[learning-rate]]

Source: HF Trainer docs (learning_rate, warmup_steps); NVIDIA training-performance guide; OLMo logbook
