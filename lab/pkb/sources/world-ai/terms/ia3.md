---
title: "IA3"
tags: [world-ai, fine-tuning]
aliases: [ia3]
---

An extremely lightweight PEFT method that learns to rescale activations with a few vectors.

IA3 learns small per-feature scaling vectors that multiply keys, values, and FFN activations, freezing all original weights. It adds even fewer parameters than LoRA, making it attractive when many tasks must be stored cheaply.

**Example:** IA3 adapts a model with a tiny number of learned scale vectors rather than weight-matrix updates.

## Related

- [[peft]]
- [[lora]]
- [[adapters]]
- [[prompt-tuning]]

Source: authored
