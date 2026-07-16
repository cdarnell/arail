---
title: "Determinism"
tags: [world-ai, inference]
aliases: [determinism, non-determinism, deterministic, stochasticity]
---

Whether a model returns the same output for the same input every time — LLMs are non-deterministic by default.

A process is deterministic if identical inputs always produce identical outputs. LLM generation is non-deterministic by default: sampling (temperature, top-p) injects randomness, and even at temperature 0, floating-point order and parallel execution (batching, GPU kernels) can cause small variations. You make it near-deterministic with greedy decoding (temperature 0), a fixed random seed, and a pinned runtime.

**Example:** Ask the same question twice at temperature 0.8 and you get two different answers; drop to temperature 0 with a fixed seed and they match — modulo hardware-level floating-point nondeterminism.

## Related

- [[temperature]]
- [[logits]]
- [[beam-search]]
- [[inference]]

Source: authored
