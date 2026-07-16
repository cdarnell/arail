---
title: "Red-Teaming"
tags: [world-ai, rl-alignment]
aliases: [red-teaming, adversarial testing]
---

Deliberately probing a model with adversarial inputs to surface harmful, unsafe, or broken behavior.

Red-teaming stress-tests a model by actively trying to make it fail — eliciting harmful content, jailbreaks, leaks, or unsafe tool use — so the gaps can be fixed before deployment. It can be manual, automated (one model attacking another), or continuous, and feeds both training data and guardrail design.

**Example:** A red team crafts roleplay prompts to bypass refusals; the successful attacks become hard negatives for the next alignment round.

## Related

- [[alignment]]
- [[guardrails]]
- [[constitutional-ai]]
- [[adversarial-swarm]]
- [[benchmark]]

Source: authored
