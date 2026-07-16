---
title: "Embedding layer"
tags: [world-ai, architecture]
aliases: [embedding-layer]
---

Maps discrete token IDs to dense vectors — the model's vocabulary lookup table.

An embedding layer is a learned matrix of shape [vocab_size, d_model] that maps each integer token ID to a dense real-valued vector. It is the first layer of all transformer language models and is often tied (shared) with the output projection (lm_head). Embedding representations encode token semantics in a continuous space.

**Example:** A tokenizer output of [1, 4823, 29892] is looked up in the embedding matrix to get three 4096-dimensional vectors as input to the first transformer block.

## Related

- [[transformer]]
- [[positional-encoding]]

Source: Goodfellow et al. — Deep Learning ch.12; HF Transformers model architecture docs
