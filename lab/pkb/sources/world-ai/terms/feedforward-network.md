---
title: "Feed-Forward Network"
tags: [world-ai, architecture]
aliases: [feedforward-network, FFN, MLP block]
---

The per-token two-layer MLP in each transformer block, where most parameters and stored knowledge live.

Each transformer block pairs attention (which mixes information across tokens) with a position-wise feed-forward network applied independently to every token: expand to a larger hidden dimension, apply a nonlinearity, project back. It holds the majority of a model's parameters and is widely viewed as where much factual knowledge is stored — and what MoE makes sparse.

**Example:** A model with hidden size 4k typically expands to ~16k inside the FFN before projecting back to 4k.

## Related

- [[transformer]]
- [[attention]]
- [[gelu]]
- [[moe]]
- [[parameter]]

Source: authored
