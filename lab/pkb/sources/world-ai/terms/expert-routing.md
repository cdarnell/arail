---
title: "Expert Routing"
tags: [world-ai, architecture]
aliases: [expert-routing]
---

How a sparse MoE assigns each token to a subset of experts so only part of the model runs per token.

Expert routing is the mechanism (usually top-k gating) that activates only a few of an MoE's many experts per token, giving large total capacity at small per-token compute. Balancing the routing so all experts are used is a central training challenge.

**Example:** With top-2 routing over 64 experts, each token uses 2 — a fraction of the full parameter count.

## Related

- [[moe]]
- [[gating-network]]
- [[feedforward-network]]
- [[parameter]]

Source: authored
