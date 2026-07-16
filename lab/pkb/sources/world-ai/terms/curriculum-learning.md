---
title: "Curriculum Learning"
tags: [world-ai, training]
aliases: [curriculum-learning]
---

Train on easier examples first, then progressively harder ones, like a teaching syllabus.

Curriculum learning orders training data from simple to complex instead of presenting it randomly, on the intuition that early easy examples build a foundation that makes hard examples learnable. It can speed convergence and improve final quality on tasks with a natural difficulty gradient.

**Example:** A math model trained on single-step problems before multi-step ones learns multi-step reasoning faster than from a shuffled mix.

## Related

- [[pretraining]]
- [[sft]]
- [[data-augmentation]]
- [[scaling-laws]]

Source: authored
