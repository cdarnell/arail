---
title: "Self-Supervised Learning"
tags: [world-ai, fundamentals]
aliases: [self-supervised-learning]
---

Create the training signal from the data itself — e.g. predict the next token — needing no human labels.

Self-supervised learning generates supervision from the raw data: mask or hold out part of an input and train the model to predict it. Next-token prediction is the self-supervised objective behind LLM pretraining, which is why models can learn from trillions of unlabeled web tokens.

**Example:** Hiding the last word of each sentence and training the model to guess it is self-supervised.

## Related

- [[pretraining]]
- [[supervised-learning]]
- [[unsupervised-learning]]
- [[transfer-learning]]

Source: authored
