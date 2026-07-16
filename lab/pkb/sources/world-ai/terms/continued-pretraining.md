---
title: "Continued pretraining"
tags: [world-ai, fine-tuning]
aliases: [continued-pretraining]
---

Resume pretraining on domain data before task fine-tuning to build domain fluency.

Continued pretraining (also: domain-adaptive pretraining, DAPT) continues the language model objective on a domain-specific corpus before instruction fine-tuning. This fills domain vocabulary into the model weights before any task-specific adaptation, improving downstream fine-tuning efficiency and final quality. The learning rate is typically lower than original pretraining to avoid catastrophic forgetting of the base model general capabilities.

**Example:** Continuing pretraining on a domain corpus for 1k steps at LR 5e-5 before LoRA fine-tuning improves downstream domain task accuracy compared to LoRA fine-tuning from the base model alone (Gururangan et al., 2020).

## Related

- [[fine-tuning]]
- [[domain-specialist-model]]
- [[catastrophic-forgetting]]

Source: Gururangan et al. — Don't Stop Pretraining arXiv:2004.10964; HF Trainer docs (language modeling)
