---
title: "Online Distillation"
tags: [world-ai, fine-tuning]
aliases: [online-distillation, codistillation]
---

Teacher and student train together at the same time instead of distilling from a frozen teacher.

In online (or co-) distillation there is no pre-trained frozen teacher: a cohort of models trains simultaneously and each learns from the others' current predictions. It removes the separate teacher-training phase and can scale across many workers, with each worker's model acting as a peer teacher.

**Example:** Four model replicas train in parallel, each adding a term that matches the averaged predictions of the other three.

## Related

- [[distillation]]
- [[self-distillation]]
- [[soft-targets]]

Source: authored
