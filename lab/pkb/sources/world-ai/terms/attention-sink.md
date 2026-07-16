---
title: "Attention Sink"
tags: [world-ai, architecture]
aliases: [attention-sink]
---

Initial tokens that attention disproportionately fixates on; preserving them stabilizes long/streaming generation.

Models learn to dump excess attention weight onto the first few tokens (an 'attention sink'). Keeping those tokens in the KV-cache while evicting middle ones lets a model stream indefinitely without the quality collapse a naive sliding window causes.

**Example:** Retaining the first 4 tokens as sinks lets a model generate past its trained context without degrading.

## Related

- [[attention]]
- [[kv-cache]]
- [[sliding-window-attention]]
- [[context-window]]

Source: authored
