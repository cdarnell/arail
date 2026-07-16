---
title: "LoRA"
tags: [world-ai, fine-tuning]
aliases: [lora, Low-Rank Adaptation]
---

Fine-tune a model by training tiny low-rank adapter matrices while the base weights stay frozen.

LoRA freezes the original weights and injects small trainable rank-decomposition matrices into each layer. You train only those low-rank matrices — often under 1% of the parameters — which slashes memory and lets a single GPU fine-tune models that would otherwise need a cluster.

**Example:** Fully fine-tuning a 7B model needs ~60GB+; with LoRA you train ~10-50MB of adapters in ~10GB, then merge or hot-load them at inference.

## Related

- [[qlora]]
- [[peft]]
- [[adapters]]
- [[fine-tune]]

Source: qukaizen/docs/TECHNIQUES.md
