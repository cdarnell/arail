---
title: "Perplexity"
tags: [world-ai, fundamentals]
aliases: [perplexity, PPL]
---

A measure of how surprised a model is by text — lower means it predicts the text better.

Perplexity is the exponentiated average negative log-likelihood a model assigns to a sequence — roughly the effective number of equally likely choices it faces each step. Lower is better, but it is an intrinsic metric, not a substitute for task benchmarks.

**Example:** A model with perplexity 10 on a test set is about as uncertain as choosing uniformly among 10 tokens each step.

## Related

- [[logits]]
- [[softmax]]
- [[tokenizer]]

Source: authored
