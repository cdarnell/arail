---
title: "Early Stopping"
tags: [world-ai, training]
aliases: [early-stopping]
---

Halt training when validation performance stops improving, to avoid overfitting.

Early stopping monitors a held-out validation metric and stops (or rolls back to the best checkpoint) once it plateaus or worsens, even if training loss is still falling. It is a simple, effective regularizer.

**Example:** Validation loss bottoms out at epoch 7 then rises; early stopping keeps the epoch-7 checkpoint.

## Related

- [[validation-set]]
- [[overfitting]]
- [[regularization]]
- [[checkpoint]]

Source: authored
