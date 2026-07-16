---
title: "Greedy Decoding"
tags: [world-ai, inference]
aliases: [greedy-decoding, argmax decoding]
---

Always pick the single highest-probability next token — deterministic but can be repetitive.

Greedy decoding takes the argmax token at every step. It is deterministic and fast, ideal when you want reproducible or single 'best' answers, but it can get stuck in repetition and miss globally better sequences that require a locally lower-probability step (which beam search or sampling can reach).

**Example:** For a factual lookup you use greedy decoding so the same prompt always returns the same answer.

## Related

- [[sampling]]
- [[beam-search]]
- [[temperature]]
- [[determinism]]

Source: authored
