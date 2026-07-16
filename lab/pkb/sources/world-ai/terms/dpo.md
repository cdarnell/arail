---
title: "DPO"
tags: [world-ai, rl-alignment]
aliases: [dpo, Direct Preference Optimization]
---

Align to preferences directly from good/bad answer pairs — no reward model or RL loop.

DPO skips RLHF's separate reward model and PPO loop, reframing alignment as a simple classification-style loss over (preferred, rejected) pairs that directly raises the likelihood of preferred answers. Simpler and more stable than PPO-based RLHF, with comparable results.

**Example:** Feed pairs like (concise correct answer = preferred, rambling answer = rejected); DPO's loss directly widens the margin between them.

## Related

- [[rlhf]]
- [[ppo]]
- [[sft]]

Source: authored
