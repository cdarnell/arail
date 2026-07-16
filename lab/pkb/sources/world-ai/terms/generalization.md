---
title: "Generalization"
tags: [world-ai, fundamentals]
aliases: [generalization]
---

How well a model performs on new, unseen data rather than the data it trained on.

Generalization is the whole point of learning: a model that only fits its training set has memorized, not learned. It is measured on held-out data and improved with more/diverse data and regularization. The train-vs-test gap is the practical signal of how well a model generalizes.

**Example:** A model that scores 95% on both train and test generalizes well; 99% train but 70% test does not.

## Related

- [[overfitting]]
- [[regularization]]
- [[eval]]
- [[baseline]]
- [[validation-set]]

Source: authored
