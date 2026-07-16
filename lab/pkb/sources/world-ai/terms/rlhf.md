---
title: "RLHF"
tags: [world-ai, rl-alignment]
aliases: [rlhf, Reinforcement Learning from Human Feedback]
---

Align a model to human preferences via a reward model trained on human rankings, then RL.

RLHF collects human comparisons of model outputs, trains a reward model to predict which response people prefer, then fine-tunes the policy with reinforcement learning (usually PPO) to maximize that reward. It is how raw pretrained models became helpful, harmless assistants.

**Example:** Given two answers to 'explain recursion', humans pick the clearer one; the reward model learns that preference; PPO nudges the model toward it.

## Related

- [[dpo]]
- [[ppo]]
- [[sft]]

Source: authored
