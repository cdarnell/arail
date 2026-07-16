---
title: "Add regularization"
tags: [world-ai, care-actions]
aliases: [add-regularization]
---

Apply dropout, weight decay, or data augmentation to reduce overfitting.

When the train/val loss gap is large (overfitting), regularization constrains the model from over-specializing to training data. Options: weight decay (L2) penalizes large weights via the optimizer; dropout randomly zeroes activations during training; data augmentation expands effective dataset size; label smoothing prevents overconfident predictions. For fine-tuning, LoRA is an implicit regularizer (low-rank constraint).

**Example:** Adding dropout=0.1 and weight_decay=0.01 to a fine-tuning run reduces the train/val gap from 1.4 to 0.6 nats.

## Related

- [[train-val-loss-gap]]
- [[catastrophic-forgetting]]
- [[dropout]]
- [[weight-decay]]

Source: Goodfellow et al. — Deep Learning ch.7; HF Trainer docs (weight_decay); PyTorch Dropout docs
