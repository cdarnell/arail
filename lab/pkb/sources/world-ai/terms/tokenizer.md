---
title: "Tokenizer"
tags: [world-ai, fundamentals]
aliases: [tokenizer, tokenization, BPE]
---

Splits text into tokens (subword units) the model actually reads, and back again.

A tokenizer converts raw text into integer token IDs (and back) using a learned vocabulary, usually via subword schemes like BPE or SentencePiece. Token count drives context limits and cost, and odd tokenization explains many model quirks.

**Example:** 'tokenization' might split into ['token', 'ization']; rare words and emoji can become many tokens, inflating cost.

## Related

- [[embeddings]]
- [[perplexity]]

Source: authored
