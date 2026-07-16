---
title: "MLX"
tags: [world-ai, formats-runtime]
aliases: [mlx]
---

Apple's array framework for running and training models on Apple Silicon's unified memory.

MLX uses the shared CPU/GPU memory of Apple Silicon for zero-copy inference and fine-tuning — no host↔device transfers and much lower power. AeroLLM targets it for Mac deployments.

**Example:** On an M-series Mac, MLX runs a streamed model against unified memory with ~83% less power than a discrete GPU.

## Related

- [[layer-streaming]]
- [[quantization]]

Source: QuKaiZen AI Dictionary
