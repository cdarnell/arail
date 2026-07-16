---
title: "Born-Again Networks"
tags: [world-ai, fine-tuning]
aliases: [born-again-networks, BAN]
---

Distill a model into a fresh copy of identical size — the student often beats the teacher.

Born-again networks distill a trained model into a new network of the same architecture and size, using the teacher's soft predictions as targets. Despite no capacity gain, the student frequently outperforms its teacher because soft labels carry richer inter-class information than hard labels. Chaining generations (teacher -> student -> next student) can compound the gain.

**Example:** A ResNet distilled into an identical ResNet using the original's softened logits scores higher than the original on the same test set.

## Related

- [[self-distillation]]
- [[distillation]]
- [[soft-targets]]

Source: authored
