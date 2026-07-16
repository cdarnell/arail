---
title: "GRPO"
tags: [world-ai, rl-alignment]
aliases: [grpo, Group Relative Policy Optimization]
---

A PPO-style RL method that drops the value network, scoring each sample relative to a group of samples for the same prompt.

Group Relative Policy Optimization estimates advantages by sampling a group of completions per prompt and comparing each to the group's average reward, removing the separate value (critic) model PPO needs. This makes RL fine-tuning cheaper and simpler, and it has been central to recent reasoning-model training.

**Example:** For one math prompt the model draws 8 answers; each is rewarded relative to the group mean, and the policy moves toward the above-average ones.

## Related

- [[ppo]]
- [[rlhf]]
- [[reward-model]]
- [[reasoning]]
- [[kl-divergence]]

Source: authored
