---
title: "Adapters"
tags: [world-ai, fine-tuning]
aliases: [adapters, adapter layers]
---

Small trainable modules inserted into a frozen model to add new skills without retraining it.

Adapters are tiny bottleneck layers added between a frozen model's existing layers; only the adapters train. They are a parameter-efficient way to teach new tasks, and you can keep a library of swappable adapters for one base. LoRA is a popular low-rank flavor of this idea.

**Example:** Ship one 7B base plus a 'legal' adapter and a 'medical' adapter; load whichever the task needs.

## Related

- [[lora]]
- [[peft]]
- [[fine-tune]]

Source: authored
