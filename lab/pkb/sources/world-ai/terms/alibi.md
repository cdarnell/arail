---
title: "ALiBi"
tags: [world-ai, architecture]
aliases: [alibi, Attention with Linear Biases]
---

Position handling that biases attention scores by distance instead of adding position embeddings.

Attention with Linear Biases adds a distance-proportional penalty to attention scores rather than using explicit positional encodings. This lets a model trained on short contexts extrapolate to longer ones at inference with less degradation.

**Example:** An ALiBi model trained at 2k tokens still behaves sensibly when run at 8k.

## Related

- [[positional-encoding]]
- [[rope]]
- [[attention]]
- [[context-window]]

Source: authored
