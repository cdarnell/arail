---
title: "Activation Checkpointing"
tags: [world-ai, training]
aliases: [activation-checkpointing, gradient checkpointing, recomputation]
---

Trade compute for memory by recomputing activations in the backward pass instead of storing them.

Activation (gradient) checkpointing discards intermediate activations during the forward pass and recomputes them when needed for backprop, cutting memory at the cost of an extra forward pass. It is essential for training large models or long sequences on limited memory.

**Example:** Checkpointing lets a model that wouldn't fit train by recomputing layer activations rather than caching them.

## Related

- [[backprop]]
- [[fsdp]]
- [[gradient-accumulation]]

Source: authored
