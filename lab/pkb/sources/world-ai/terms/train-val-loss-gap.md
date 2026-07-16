---
title: "Train/val loss gap"
tags: [world-ai, symptoms]
aliases: [train-val-loss-gap]
---

Validation loss significantly worse than training loss — generalization failure.

A large gap between training and validation loss signals overfitting: the model has memorized training data rather than learning to generalize. The gap widens over epochs as the model fits noise. The severity of overfitting is proportional to the gap size. Common during full fine-tuning of large models on small datasets.

**Example:** After epoch 3 of full fine-tuning on 5k examples, train loss is 0.4 but val loss is 1.8 and rising — classic overfitting.

## Related

- [[overfitting]]
- [[catastrophic-forgetting]]
- [[add-regularization]]
- [[early-stopping]]

Source: Goodfellow et al. — Deep Learning ch.7 (regularization); HF Trainer docs (evaluation_strategy)
