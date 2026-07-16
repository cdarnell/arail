---
title: "SwiGLU"
tags: [world-ai, architecture]
aliases: [swiglu]
---

A gated activation for the feed-forward block that tends to beat plain GELU/ReLU at equal size.

SwiGLU combines a Swish activation with a gating mechanism: the FFN computes two projections and uses one to gate the other. It consistently improves quality over ReLU/GELU FFNs and is standard in recent LLMs, usually with a widened hidden dimension to keep parameter count comparable.

**Example:** Replacing the GELU FFN with SwiGLU nudges benchmark scores up at matched parameters.

## Related

- [[gelu]]
- [[feedforward-network]]
- [[activation-function]]

Source: authored
