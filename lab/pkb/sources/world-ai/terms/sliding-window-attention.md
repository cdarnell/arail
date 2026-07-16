---
title: "Sliding-Window Attention"
tags: [world-ai, architecture]
aliases: [sliding-window-attention, local attention]
---

Each token attends only to a fixed window of nearby tokens, making attention linear in length.

Sliding-window attention restricts each token to a fixed-size local neighborhood instead of the full sequence, reducing attention cost from quadratic to linear in context length. Stacking layers still propagates information globally (a token's window overlaps its neighbors'), so long-range signal survives at far lower cost — used in models built for long contexts.

**Example:** With a 4k window, token 100,000 attends only to tokens 96,000-100,000, yet deep layers still relay information from the document start.

## Related

- [[attention]]
- [[sparse-attention]]
- [[context-window]]
- [[flashattention]]

Source: authored
