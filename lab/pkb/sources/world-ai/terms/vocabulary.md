---
title: "Vocabulary"
tags: [world-ai, fundamentals]
aliases: [vocabulary, vocab]
---

The fixed set of tokens a model knows; its size sets the width of the input and output layers.

A model's vocabulary is the complete set of tokens its tokenizer can produce, fixed at training time. Its size (often 32k-256k) sets the dimensions of the embedding table and the final softmax: every step the model produces a distribution over the whole vocabulary. Larger vocabularies pack more text per token but enlarge those layers.

**Example:** With a 128k vocabulary the final layer outputs a 128k-long logit vector at each step.

## Related

- [[tokenizer]]
- [[embeddings]]
- [[logits]]
- [[softmax]]

Source: authored
