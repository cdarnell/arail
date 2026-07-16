---
title: "torch.compile"
tags: [world-ai, performance]
aliases: [torch-compile, torch compile]
---

PyTorch's just-in-time compiler that traces and optimizes a model into faster fused kernels.

torch.compile captures a model's operations into a graph and lowers it through a backend (e.g. Inductor/Triton) to fused, optimized kernels, often yielding speedups with a one-line change. It brings ahead-of-time-style optimization to otherwise eager PyTorch code.

**Example:** Wrapping a model in torch.compile fuses ops and speeds training/inference with no model changes.

## Related

- [[kernel-fusion]]
- [[triton]]
- [[cuda-graphs]]
- [[pytorch]]

Source: authored
