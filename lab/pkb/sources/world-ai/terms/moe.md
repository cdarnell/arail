---
title: "MoE"
tags: [world-ai, architecture]
aliases: [moe, Mixture of Experts]
---

A model split into many expert sub-networks where a router activates only a few per token.

Mixture-of-Experts replaces a dense layer with many parallel expert networks plus a router that picks a small subset (e.g., 2 of 64) per token. Total parameters balloon while compute per token stays modest — huge capacity at a fraction of dense FLOPs.

**Example:** A 671B-parameter MoE might activate only ~37B per token, so it runs far cheaper than a dense 671B model.

## Related

- [[transformer]]
- [[attention]]
- [[layer-streaming]]

Source: authored
