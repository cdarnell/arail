---
title: "Constitutional AI"
tags: [world-ai, rl-alignment]
aliases: [constitutional-ai, CAI]
---

Align a model to an explicit written set of principles, using the model to critique and revise its own outputs.

Constitutional AI aligns a model against a 'constitution' — a list of written principles — by having the model critique and revise its responses to better follow them, then training on those revisions and on AI-generated preference labels (RLAIF). It reduces reliance on large volumes of human harm-labeling and makes the values steering the model explicit and auditable.

**Example:** The model rewrites a reply that violated 'avoid giving harmful instructions', and the revised version becomes a training target.

## Related

- [[rlaif]]
- [[alignment]]
- [[rlhf]]
- [[red-teaming]]
- [[guardrails]]

Source: authored
