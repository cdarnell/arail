---
title: "IPO"
tags: [world-ai, rl-alignment]
aliases: [ipo, Identity Preference Optimization]
---

A DPO variant that adds regularization to avoid overfitting to deterministic preferences.

Identity Preference Optimization reformulates the preference objective to directly control how far the policy moves, addressing a DPO failure mode where near-deterministic preferences push the model to extremes. It is one of several offshoots refining direct preference optimization.

**Example:** Where DPO overfits to a clear win, IPO's regularizer keeps the policy from collapsing.

## Related

- [[dpo]]
- [[kto]]
- [[orpo]]
- [[reward-model]]
- [[preference-data]]

Source: authored
