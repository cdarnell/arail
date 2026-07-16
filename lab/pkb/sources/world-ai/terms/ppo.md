---
title: "PPO"
tags: [world-ai, rl-alignment]
aliases: [ppo, Proximal Policy Optimization]
---

The RL algorithm classically used to optimize a model against a reward model in RLHF.

PPO is a policy-gradient method that improves a model while clipping each update to stay close to the previous policy, preventing destructive jumps. In RLHF it is the optimizer that pushes the model to maximize reward-model scores.

**Example:** During RLHF, PPO raises the probability of high-reward responses but clips the step if the new policy strays too far from the old one.

## Related

- [[rlhf]]
- [[dpo]]

Source: authored
