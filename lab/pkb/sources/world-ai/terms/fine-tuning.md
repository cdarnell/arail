---
title: "Fine-tuning"
tags: [world-ai, fine-tuning]
aliases: [fine-tuning]
---

Adapt a pretrained model to a target task or domain by continued gradient updates.

Fine-tuning initializes a model from pretrained weights and continues training on a task-specific or domain-specific dataset. Full fine-tuning updates all parameters; PEFT methods update only a small subset. Fine-tuning on too little data or for too many epochs risks catastrophic forgetting. Fine-tuning is the primary path from a general-purpose foundation model to a domain-specialist model.

**Example:** Starting from Llama-2-7B weights, fine-tuning for 3 epochs on 50k domain-specific examples with LoRA produces a domain-adapted specialist.

## Related

- [[lora]]
- [[peft]]
- [[catastrophic-forgetting]]
- [[continued-pretraining]]

Source: Goodfellow et al. — Deep Learning ch.15 (transfer learning); HF Trainer docs; LoRA arXiv:2106.09685
