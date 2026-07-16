---
title: "Teacher Model"
tags: [world-ai, qukaizen]
aliases: [teacher]
---

The large frontier model whose reasoning is distilled into a small student.

In distillation the teacher is the big, capable model (400B+) that generates reasoning traces and judgments; the student learns to reproduce its competence in-domain. QuKaiZen uses two-tier teachers for breadth and depth.

**Example:** A 400B teacher writes step-by-step solutions that train a 3B student to match it in-domain.

## Related

- [[student]]
- [[distillation]]

Source: QuKaiZen AI Dictionary
