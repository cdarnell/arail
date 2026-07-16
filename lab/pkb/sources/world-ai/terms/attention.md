---
title: "Attention"
tags: [world-ai, architecture]
aliases: [attention, scaled dot-product attention]
---

The mechanism that lets each token weigh and pull information from every other token.

Attention computes, for each token, a weighted sum of all tokens' value vectors, where weights come from the similarity (dot product) of its query with others' keys. It is how transformers model long-range relationships, and its quadratic cost is what FlashAttention and the KV-cache optimize.

**Example:** In 'the cat sat because it was tired', attention links 'it' back to 'cat' by giving that pair a high weight.

## Related

- [[transformer]]
- [[flashattention]]
- [[kv-cache]]
- [[softmax]]

Source: authored
