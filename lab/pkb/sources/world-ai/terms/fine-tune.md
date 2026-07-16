---
title: "Fine-tune"
tags: [world-ai, fine-tuning]
aliases: [fine-tune]
---

Continue training a pretrained model on new data to specialize it for a task or domain.

Fine-tuning takes a general pretrained model and trains it further on a focused dataset so it adapts to a domain, style, or task. It can be full (all weights) or parameter-efficient (LoRA/PEFT), and is the bridge from a generic base to a useful specialist.

**Example:** Fine-tune a base 7B on 30 years of Linux-kernel commits and it starts reasoning like a kernel engineer.

## Related

- [[sft]]
- [[lora]]
- [[peft]]
- [[distillation]]

Source: authored
