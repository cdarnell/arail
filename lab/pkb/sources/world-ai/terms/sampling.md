---
title: "Sampling"
tags: [world-ai, inference]
aliases: [sampling, stochastic decoding]
---

Drawing the next token randomly from the model's probability distribution rather than always taking the top one.

Sampling selects each next token by drawing from the model's predicted distribution (often after temperature, top-k, or top-p shaping), introducing controlled randomness. It produces more diverse, natural text than greedy decoding and is the basis for generating multiple candidate answers in self-distillation and best-of-N methods.

**Example:** With sampling on, asking the same question twice yields two different but valid phrasings.

## Related

- [[temperature]]
- [[top-k]]
- [[top-p]]
- [[greedy-decoding]]
- [[beam-search]]

Source: authored
