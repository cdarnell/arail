---
title: "Prompt Tuning"
tags: [world-ai, fine-tuning]
aliases: [prompt-tuning, soft prompts]
---

Learn a small set of continuous 'soft prompt' vectors while freezing the model, to steer behavior cheaply.

Prompt tuning prepends a handful of trainable embedding vectors to the input and trains only those, leaving the model frozen. It is among the most parameter-light adaptations, storing just the soft prompt per task, though it is usually less expressive than LoRA.

**Example:** A task is adapted by learning 20 soft-prompt vectors instead of touching any model weights.

## Related

- [[prefix-tuning]]
- [[peft]]
- [[lora]]
- [[adapters]]

Source: authored
