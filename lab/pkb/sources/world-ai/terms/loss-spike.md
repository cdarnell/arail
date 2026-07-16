---
title: "Loss spike"
tags: [world-ai, symptoms]
aliases: [loss-spike]
---

A sharp, transient jump in loss that may or may not recover.

A brief jump in training loss — often 2–10× the running baseline — that either recovers within a few hundred steps (a recoverable spike) or becomes a divergence. Spikes correlate with bad batches, data contamination, or a learning rate that is at the boundary of instability. Distinguishing recoverable from diverging requires observing the trend after the spike.

**Example:** At step 8k, loss jumps from 2.1 to 4.8 then slowly returns to 2.3 over the next 200 steps — a recoverable spike consistent with a contaminated batch.

## Related

- [[diverging-loss]]
- [[learning-rate-too-high]]
- [[duplicate-contaminated-data]]
- [[gradient-clipping]]

Source: OLMo training logbook; Karpathy nanoGPT notes on loss spikes
