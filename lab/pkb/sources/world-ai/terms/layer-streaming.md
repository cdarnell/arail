---
title: "Layer Streaming"
tags: [world-ai, performance]
aliases: [layer-streaming, layer-by-layer inference]
---

Load one transformer layer from disk, compute, discard — running 400B+ models on tiny VRAM.

Layer-streaming inference (AeroLLM's core primitive) streams a model layer by layer from SSD: load a layer's weights, compute, free, repeat. It trades latency for the ability to run frontier-scale teachers (70B-671B) on commodity hardware with a few GB of VRAM.

**Example:** A 671B MoE at Q4 streams off a 1TB SSD on a MacBook — slow per token, but a background swarm does not mind waiting for depth.

## Related

- [[aerollm]]
- [[speculative-decoding]]
- [[quantization]]
- [[super-skill]]

Source: knowledge_base/wiki/concepts/Layer_Streaming_Inference.md
