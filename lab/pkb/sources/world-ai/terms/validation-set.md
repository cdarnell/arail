---
title: "Validation Set"
tags: [world-ai, training]
aliases: [validation-set]
---

Held-out data used to tune and monitor training, kept separate from the final test set.

A validation (dev) set is data the model never trains on, used to pick hyperparameters, trigger early stopping, and watch for overfitting during training. It must stay separate from the test set, which is touched only once for the final, unbiased estimate.

**Example:** You pick the learning rate by validation-set loss, then report the chosen model on the untouched test set.

## Related

- [[eval]]
- [[generalization]]
- [[overfitting]]
- [[early-stopping]]
- [[data-contamination]]

Source: authored
