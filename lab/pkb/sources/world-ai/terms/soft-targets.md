---
title: "Soft Targets"
tags: [world-ai, fine-tuning]
aliases: [soft-targets, soft labels, dark knowledge]
---

A teacher's full probability distribution used as the training target, not just the single correct label.

Soft targets are the teacher's softened output probabilities (often via a temperature) over all classes or tokens. They encode 'dark knowledge' — how the teacher rates the wrong answers relative to each other — which teaches the student far more than a one-hot label. Matching soft targets is the core signal in classic knowledge distillation.

**Example:** On an image of a dog, a hard label says only 'dog'; the soft target also says 'wolf 8%, cat 0.1%', telling the student dogs resemble wolves more than cats.

## Related

- [[distillation]]
- [[logits]]
- [[softmax]]
- [[temperature]]
- [[born-again-networks]]

Source: authored
