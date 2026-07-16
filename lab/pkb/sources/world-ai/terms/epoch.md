---
title: "Epoch"
tags: [world-ai, training]
aliases: [epoch]
---

One full pass of the optimizer over the entire training dataset.

An epoch is a complete sweep through all training examples. Small fine-tuning runs may use several epochs; large pretraining often uses roughly one pass over a huge corpus, since repeating data risks memorization. Tracking loss per epoch helps spot overfitting.

**Example:** Fine-tuning on 10k examples for 3 epochs shows the model each example three times.

## Related

- [[batch-size]]
- [[overfitting]]
- [[pretraining]]
- [[sft]]

Source: authored
