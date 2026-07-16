---
title: "Warmup"
tags: [world-ai, training]
aliases: [warmup, learning-rate warmup]
---

Ramping the learning rate up from near zero over the first steps to avoid early instability.

Learning-rate warmup starts the LR small and increases it over the first few hundred or thousand steps before the main schedule (often cosine decay). Early gradients are noisy; warmup prevents large destabilizing updates while the optimizer's statistics settle.

**Example:** 500 warmup steps ramping to 2e-4, then cosine decay to near zero over the run.

## Related

- [[adamw]]
- [[gradient]]

Source: authored
