---
title: "CUDA"
tags: [world-ai, formats-runtime]
aliases: [cuda, CUDA]
---

NVIDIA's platform/language for general-purpose GPU computing — the substrate most ML runs on.

CUDA is NVIDIA's parallel-computing API and toolkit that lets code run on GPUs. Frameworks compile their tensor ops down to CUDA kernels (and libraries like cuBLAS/cuDNN), which is why GPU availability and CUDA versions dominate ML ops.

**Example:** A version mismatch between a PyTorch build and the installed CUDA toolkit is the classic 'it will not see the GPU' bug.

## Related

- [[triton]]
- [[flashattention]]

Source: authored
