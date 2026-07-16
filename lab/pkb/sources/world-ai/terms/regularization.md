---
title: "Regularization"
tags: [world-ai, training]
aliases: [regularization]
---

Any technique that constrains a model to generalize better rather than memorize the training set.

Regularization covers methods that trade a little training-set fit for better generalization: weight decay, dropout, data augmentation, early stopping, and label smoothing among them. The goal is to reduce overfitting so the model performs on unseen data, not just the data it saw.

**Example:** Adding dropout and weight decay closes a gap where the model scored 99% on train but 80% on validation.

## Related

- [[overfitting]]
- [[dropout]]
- [[weight-decay]]
- [[data-augmentation]]

Source: authored
