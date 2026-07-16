---
title: "Kernel Fusion"
tags: [world-ai, performance]
aliases: [kernel-fusion]
---

Combine multiple GPU operations into one kernel to cut memory round-trips and launch overhead.

Kernel fusion merges several elementwise or sequential operations into a single GPU kernel so intermediate results stay in fast on-chip memory instead of being written to and read from global memory. FlashAttention is a famous fused kernel; compilers like torch.compile fuse automatically.

**Example:** Fusing the attention softmax and matmuls (FlashAttention) avoids materializing the huge score matrix in memory.

## Related

- [[flashattention]]
- [[cuda-graphs]]
- [[torch-compile]]
- [[triton]]
- [[memory-bandwidth]]

Source: authored
