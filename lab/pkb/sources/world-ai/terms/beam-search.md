---
title: "Beam Search"
tags: [world-ai, inference]
aliases: [beam-search, beam search]
---

A decoding strategy that keeps the top-k partial sequences each step to find a higher-probability output.

Beam search explores several candidate sequences (beams) in parallel, expanding and pruning to the k most probable at each step. It yields higher-likelihood, more deterministic outputs than greedy decoding — good for translation and structured tasks, but it can be bland for open-ended generation.

**Example:** With beam width 4, the decoder tracks the 4 best running sequences and returns the best completed one.

## Related

- [[temperature]]
- [[logits]]
- [[inference]]

Source: authored
