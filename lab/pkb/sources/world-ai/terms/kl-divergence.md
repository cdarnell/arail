---
title: "KL Divergence"
tags: [world-ai, rl-alignment]
aliases: [kl-divergence, Kullback-Leibler divergence, KL penalty]
---

A measure of how far one distribution is from another — used to keep an RL-tuned model near its base.

KL divergence quantifies how much one probability distribution diverges from a reference. In RLHF it is added as a penalty so the policy doesn't drift too far from the original (SFT) model while chasing reward, preventing reward hacking and gibberish. It also underlies distillation objectives that match a teacher's distribution.

**Example:** A KL penalty stops a model from collapsing to a few high-reward but degenerate phrases during PPO.

## Related

- [[rlhf]]
- [[ppo]]
- [[reward-model]]
- [[soft-targets]]
- [[distillation]]

Source: authored
