---
title: "In-Context Learning"
tags: [world-ai, fundamentals]
aliases: [in-context-learning, ICL]
---

A model learns a task from examples in its prompt at inference time, with no weight updates.

In-context learning is the ability of large models to infer a task purely from instructions and examples placed in the prompt, adapting behavior without any gradient update. It is what makes few-shot prompting work and is an emergent property that strengthens with scale.

**Example:** Shown three 'English -> pirate' translations in the prompt, the model translates a fourth correctly without being trained for it.

## Related

- [[few-shot]]
- [[zero-shot]]
- [[prompt]]
- [[emergent-abilities]]

Source: authored
