---
title: "Knowledge distillation"
tags: [world-ai, fine-tuning]
aliases: [knowledge-distillation]
---

Transfer knowledge from a large teacher model to a smaller student model.

Knowledge distillation (Hinton et al., 2015) trains a smaller student model to match the output distribution (soft targets/logits) of a larger teacher model, rather than hard labels. The teacher's soft predictions encode richer information about class relationships than one-hot labels. Distillation can significantly improve a small model's performance without access to the teacher at inference time.

**Example:** A 1B student model trained to match the token-probability outputs of a 70B teacher achieves much better perplexity than the same student trained on hard labels alone.

## Related

- [[teacher-student-training]]
- [[soft-targets]]
- [[small-language-model]]

Source: Hinton et al. — Distilling the Knowledge in a Neural Network arXiv:1503.02531; Goodfellow et al. — Deep Learning ch.7
