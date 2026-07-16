---
title: "Sparse Attention"
tags: [world-ai, architecture]
aliases: [sparse-attention]
---

Compute attention over only a chosen subset of token pairs instead of all of them.

Sparse attention replaces the dense all-pairs attention matrix with a structured or learned subset — local windows, strided/dilated patterns, global tokens, or routed blocks — to cut the quadratic cost of long sequences. The pattern is designed so information can still flow across the whole sequence in a few hops.

**Example:** A pattern mixing local windows with a handful of global 'summary' tokens lets a long document be processed without the full N x N matrix.

## Related

- [[sliding-window-attention]]
- [[attention]]
- [[flashattention]]

Source: authored
