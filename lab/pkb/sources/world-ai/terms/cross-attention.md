---
title: "Cross-Attention"
tags: [world-ai, architecture]
aliases: [cross-attention]
---

Attention where queries come from one sequence and keys/values from another.

In cross-attention the queries are drawn from one stream (e.g. the text being generated) while keys and values come from a different stream (e.g. an encoded image or source sentence). It is how encoder-decoder and multimodal models let one modality or sequence condition on another, in contrast to self-attention where all three come from the same sequence.

**Example:** A translation decoder uses cross-attention to look back at the encoded source sentence while emitting each target word.

## Related

- [[attention]]
- [[encoder-decoder]]
- [[multi-head-attention]]

Source: authored
