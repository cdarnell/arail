---
title: "Teacher–student training"
tags: [world-ai, fine-tuning]
aliases: [teacher-student-training]
---

A large teacher model guides a smaller student model's training.

The teacher-student framework uses a fixed, high-quality teacher model to provide training signal for a smaller student. The student is trained to minimize the difference between its predictions and the teacher's predictions (soft targets, intermediate representations, or both). A common pattern is to use a large frontier model as the teacher and a smaller, deployable model as the student.

**Example:** During distillation, the student receives the same input as the teacher and minimizes KL divergence between its logits and the teacher's softened logits (temperature T=4).

## Related

- [[knowledge-distillation]]
- [[soft-targets]]
- [[build-time-teacher]]

Source: Hinton et al. — Distilling the Knowledge arXiv:1503.02531; HF trl docs (knowledge distillation)
