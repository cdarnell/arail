---
title: "Verifier"
tags: [world-ai, performance]
aliases: [verifier]
---

The target-model pass that accepts or corrects speculatively drafted tokens.

In speculative decoding the verifier is the large model's single forward pass that checks the draft's proposed tokens — keeping the correct prefix and resampling the first mismatch — which guarantees the same distribution as decoding normally.

**Example:** Of 5 drafted tokens the verifier accepts 4 and corrects the 5th, all in one pass.

## Related

- [[speculative-decoding]]
- [[draft-model]]

Source: QuKaiZen AI Dictionary
