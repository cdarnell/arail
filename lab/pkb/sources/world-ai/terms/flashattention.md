---
title: "FlashAttention"
tags: [world-ai, performance]
aliases: [flashattention, Flash Attention]
---

An exact attention kernel that is fast and memory-light by never materializing the full attention matrix.

FlashAttention computes exact attention in tiles that stay in fast on-chip SRAM, avoiding the quadratic N-by-N matrix in slow HBM. It cuts memory from quadratic to linear and speeds up training and inference, enabling much longer contexts.

**Example:** Swapping standard attention for FlashAttention-2 can train a long-context model ~2x faster with far less memory.

## Related

- [[attention]]
- [[kv-cache]]
- [[transformer]]

Source: authored
