---
title: "RoPE"
tags: [world-ai, architecture]
aliases: [rope, Rotary Position Embedding]
---

Encodes token position by rotating query/key vectors — the dominant positional scheme in modern LLMs.

Rotary Position Embeddings inject position by rotating query and key vectors by an angle proportional to their position, so attention naturally depends on relative distance. RoPE extrapolates to longer contexts better than learned absolute embeddings and underlies most current LLMs.

**Example:** RoPE scaling tricks (NTK, YaRN) stretch a model trained at 4k context to 32k+ by adjusting the rotation frequencies.

## Related

- [[attention]]
- [[transformer]]
- [[embeddings]]

Source: authored
