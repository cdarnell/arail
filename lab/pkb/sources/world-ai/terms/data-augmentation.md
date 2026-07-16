---
title: "Data Augmentation"
tags: [world-ai, training]
aliases: [data-augmentation]
---

Expand or vary training data with label-preserving transformations to improve robustness.

Data augmentation synthesizes additional training examples by transforming existing ones in ways that preserve meaning — paraphrasing, back-translation, noise injection for text; crops and flips for images. It enlarges effective dataset size and improves generalization, and in LLMs increasingly means generating synthetic data with another model.

**Example:** Paraphrasing each instruction five ways quadruples a fine-tuning set and makes the model robust to phrasing.

## Related

- [[regularization]]
- [[sft]]
- [[self-distillation]]
- [[curriculum-learning]]

Source: authored
