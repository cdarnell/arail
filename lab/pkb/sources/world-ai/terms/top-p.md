---
title: "Top-p (Nucleus) Sampling"
tags: [world-ai, inference]
aliases: [top-p, nucleus sampling]
---

Sample from the smallest set of top tokens whose probabilities sum to p — an adaptive cutoff.

Top-p (nucleus) sampling keeps the smallest set of most-probable tokens whose cumulative probability reaches p, then samples from that set. Unlike fixed top-k, the cutoff adapts to the distribution's shape: wide when the model is uncertain, narrow when it's confident. It is a common default for open-ended generation.

**Example:** With p=0.9, a confident step may consider just 3 tokens while an open-ended one considers 50.

## Related

- [[top-k]]
- [[sampling]]
- [[temperature]]
- [[greedy-decoding]]

Source: authored
