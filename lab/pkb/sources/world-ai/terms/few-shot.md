---
title: "Few-Shot"
tags: [world-ai, fundamentals]
aliases: [few-shot, few-shot prompting]
---

Prompting a model with a handful of worked examples to demonstrate the desired task.

Few-shot prompting includes a small number of input-output examples in the prompt so the model infers the pattern and applies it to a new input — relying on in-context learning. It often sharply beats zero-shot on format-sensitive or unusual tasks, at the cost of longer prompts.

**Example:** Giving two examples of the exact JSON shape you want makes the model emit a third in the same shape.

## Related

- [[zero-shot]]
- [[in-context-learning]]
- [[prompt]]
- [[chain-of-thought]]

Source: authored
