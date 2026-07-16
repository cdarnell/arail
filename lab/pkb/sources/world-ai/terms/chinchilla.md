---
title: "Chinchilla Scaling"
tags: [world-ai, training]
aliases: [chinchilla, compute-optimal scaling]
---

The finding that, for a fixed compute budget, model size and training tokens should grow together.

Chinchilla showed that many large models were undertrained: for compute-optimal training, parameters and training tokens should scale in roughly equal proportion (~20 tokens per parameter as a rule of thumb). It reframed how teams allocate compute between bigger models and more data.

**Example:** Chinchilla-optimal guidance says a 7B model wants ~140B training tokens, not far fewer.

## Related

- [[scaling-laws]]
- [[pretraining]]
- [[parameter]]

Source: authored
