---
title: "DoRA"
tags: [world-ai, fine-tuning]
aliases: [dora, Weight-Decomposed Low-Rank Adaptation]
---

A LoRA refinement that decomposes weight updates into magnitude and direction for better quality.

Weight-Decomposed Low-Rank Adaptation splits each weight into a magnitude and a direction, applying the low-rank update to the direction while learning magnitude separately. It often closes the gap between LoRA and full fine-tuning at similar cost.

**Example:** Swapping LoRA for DoRA on the same budget recovers a couple points of accuracy toward full fine-tuning.

## Related

- [[lora]]
- [[qlora]]
- [[peft]]
- [[adapters]]

Source: authored
