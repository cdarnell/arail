---
title: "Reward Model"
tags: [world-ai, rl-alignment]
aliases: [reward-model, RM, preference model]
---

A model trained to score outputs by human preference, providing the reward signal for RLHF.

A reward model is trained on human comparisons (A is better than B) to predict a scalar quality score for any output. In RLHF this learned reward stands in for expensive human feedback, guiding the policy model via PPO or similar. Its accuracy and robustness to gaming bound the quality of the aligned model.

**Example:** Given two assistant replies, the reward model assigns the more helpful, harmless one a higher score, steering training toward it.

## Related

- [[rlhf]]
- [[ppo]]
- [[dpo]]
- [[alignment]]
- [[preference-data]]

Source: authored
