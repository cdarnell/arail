---
title: "Label Smoothing"
tags: [world-ai, training]
aliases: [label-smoothing]
---

Soften one-hot targets slightly so the model doesn't become over-confident.

Label smoothing replaces hard 0/1 targets with values like 0.9/0.1 spread over classes, discouraging the model from driving any probability to extremes. It improves calibration and generalization and connects conceptually to the soft targets used in distillation.

**Example:** Targeting 0.9 for the correct token instead of 1.0 keeps the model from over-confident logits.

## Related

- [[soft-targets]]
- [[cross-entropy]]
- [[regularization]]
- [[overfitting]]

Source: authored
