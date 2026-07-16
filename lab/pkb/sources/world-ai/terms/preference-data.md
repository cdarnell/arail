---
title: "Preference Data"
tags: [world-ai, rl-alignment]
aliases: [preference-data, comparison data, pairwise preferences]
---

Datasets of 'A is better than B' human judgments used to train reward models or do DPO.

Preference data consists of prompts paired with two or more candidate responses and a human (or AI) judgment of which is better. It is the raw material for reward modeling and for direct methods like DPO, encoding the values and quality bar the model should be aligned to.

**Example:** Annotators see two summaries and pick the more faithful one; thousands of such picks train the reward model.

## Related

- [[reward-model]]
- [[rlhf]]
- [[dpo]]
- [[rlaif]]
- [[alignment]]

Source: authored
