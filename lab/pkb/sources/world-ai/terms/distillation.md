---
title: "Distillation"
tags: [world-ai, fine-tuning]
aliases: [distillation, knowledge distillation]
---

Transfer a big teacher model's behavior into a small student model.

Knowledge distillation trains a small student to mimic a large teacher — matching its outputs, probabilities, or reasoning traces — so the student captures much of the teacher's capability at a fraction of the size and cost. It is the core of QuKaiZen's pipeline.

**Example:** A 3B student trained on a 400B teacher's chain-of-thought traces can match the teacher in-domain while running on a laptop.

## Related

- [[scotd]]
- [[raft]]
- [[super-skill]]
- [[fine-tune]]

Source: authored
