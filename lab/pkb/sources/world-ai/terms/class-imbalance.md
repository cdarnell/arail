---
title: "Class imbalance"
tags: [world-ai, conditions]
aliases: [class-imbalance]
---

Training data is dominated by a few classes — rare classes are ignored.

When training data has severely unequal class frequencies, the model minimizes loss by predicting the majority class, achieving high accuracy while performing poorly on rare classes. The model has not learned the minority distribution. Addressed by oversampling rare classes, undersampling majority, loss reweighting, or focal loss.

**Example:** A classifier trained on data with 95% class-A and 5% class-B achieves 95% accuracy by always predicting class-A — class-B recall is near zero.

## Related

- [[noisy-labels]]
- [[distribution-shift]]
- [[add-regularization]]

Source: Goodfellow et al. — Deep Learning ch.5; PyTorch WeightedRandomSampler docs
