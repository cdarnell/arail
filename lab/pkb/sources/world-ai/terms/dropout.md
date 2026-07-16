---
title: "Dropout"
tags: [world-ai, training]
aliases: [dropout, dropout regularization]
---

Randomly zeroing activations during training to prevent overfitting.

Dropout randomly sets a fraction of activations to zero each training step, forcing the network not to rely on any single unit and improving generalization. It is disabled at inference. Large pretraining often uses little or none, but it is common when fine-tuning on small data.

**Example:** Dropout 0.1 on a fine-tune randomly drops 10% of activations per step to curb overfitting on a small dataset.

## Related

- [[backprop]]
- [[fine-tune]]
- [[layernorm]]

Source: authored
