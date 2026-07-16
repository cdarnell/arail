---
title: "Triton"
tags: [world-ai, formats-runtime]
aliases: [triton, OpenAI Triton]
---

A Python-like language for writing fast GPU kernels without hand-writing CUDA C++.

Triton (from OpenAI) lets researchers write custom GPU kernels in a Python-like syntax that compiles to efficient code, making fused high-performance ops far easier to author. Many modern kernels, including FlashAttention implementations, are written in Triton.

**Example:** A fused softmax written in about 30 lines of Triton can beat a naive PyTorch version by a wide margin.

## Related

- [[cuda]]
- [[flashattention]]

Source: authored
