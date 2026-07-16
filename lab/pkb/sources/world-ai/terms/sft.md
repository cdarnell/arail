---
title: "SFT"
tags: [world-ai, training]
aliases: [sft, Supervised Fine-Tuning]
---

Plain supervised training on curated input to output examples — the first step of post-training.

SFT fine-tunes a pretrained model on labeled prompt/response pairs so it learns to follow instructions in a target format or domain. It is the foundation step before preference alignment (RLHF/DPO) and the simplest way to specialize a base model.

**Example:** Train on 10k (instruction, ideal answer) pairs so a base model answers like a helpful assistant instead of just continuing text.

## Related

- [[rlhf]]
- [[dpo]]
- [[fine-tune]]
- [[lora]]

Source: authored
