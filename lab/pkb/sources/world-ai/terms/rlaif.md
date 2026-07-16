---
title: "RLAIF"
tags: [world-ai, rl-alignment]
aliases: [rlaif, RL from AI Feedback]
---

Like RLHF, but the preference labels come from an AI judge instead of (or alongside) humans.

Reinforcement Learning from AI Feedback replaces human preference labels with judgments from a capable model, often guided by a written set of principles. It scales alignment data far beyond what human annotation allows and is the mechanism behind constitutional approaches; quality hinges on the judge model and the principles it follows.

**Example:** A judge model labels which of two responses better follows a 'be helpful and harmless' rubric, and those labels train the reward model.

## Related

- [[rlhf]]
- [[constitutional-ai]]
- [[reward-model]]
- [[preference-data]]
- [[alignment]]

Source: authored
