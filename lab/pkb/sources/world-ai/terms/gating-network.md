---
title: "Gating Network"
tags: [world-ai, architecture]
aliases: [gating-network, router, gate network]
---

The router in a mixture-of-experts that decides which experts handle each token.

In an MoE layer the gating network scores the experts for each token and routes it to the top-k, weighting their outputs. Its design governs load balance and quality; poor gating leaves experts under-used or overloaded.

**Example:** The gating network sends a code token to the 'programming' experts and a poem token elsewhere.

## Related

- [[moe]]
- [[expert-routing]]
- [[feedforward-network]]

Source: authored
