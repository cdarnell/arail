---
title: "Pretraining"
tags: [world-ai, training]
aliases: [pretraining, base training]
---

The first, largest training stage: learn general language/knowledge from a huge unlabeled corpus.

Pretraining trains a model from scratch on a massive, mostly unlabeled corpus with a self-supervised objective (usually next-token prediction). It produces a 'base model' with broad knowledge and capabilities but no instruction-following polish; later stages (SFT, alignment) specialize it. It dominates the total compute budget.

**Example:** A base model pretrained on trillions of web tokens can complete text but won't reliably follow 'summarize this' until fine-tuned.

## Related

- [[sft]]
- [[fine-tune]]
- [[scaling-laws]]
- [[loss-function]]
- [[transformer]]

Source: authored
