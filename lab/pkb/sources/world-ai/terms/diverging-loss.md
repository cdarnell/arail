---
title: "Diverging loss"
tags: [world-ai, symptoms]
aliases: [diverging-loss]
---

Training loss climbs without bound instead of decreasing.

Loss increases monotonically or oscillates upward past warmup, often reaching inf or NaN. Distinct from a transient loss spike that self-recovers. Divergence means the optimizer is not converging to any useful basin — the run must be restarted from a checkpoint after the root cause is fixed.

**Example:** At step 4k the loss leaves its downward trend and rises every logging step until printing NaN. The OLMo logbook records this pattern with a hyperparameter rollback as the fix.

## Related

- [[learning-rate-too-high]]
- [[fp16-overflow]]
- [[nan-loss]]
- [[learning-rate]]

Source: PyTorch amp docs; OLMo training logbook (EleutherAI/OLMo, 2024)
