---
title: "Reward Hacking"
tags: [world-ai, rl-alignment]
aliases: [reward-hacking, specification gaming]
---

When a model maximizes the reward signal in unintended ways that don't reflect true quality.

Reward hacking (specification gaming) happens when the policy finds shortcuts that score high under an imperfect reward model without actually being good — verbosity, flattery, or exploiting reward-model blind spots. It is the central failure mode that KL penalties and better reward models try to contain.

**Example:** A model learns to pad answers with confident filler because the reward model rates length as quality.

## Related

- [[reward-model]]
- [[rlhf]]
- [[ppo]]
- [[kl-divergence]]
- [[sycophancy]]

Source: authored
