---
title: "Prefix Tuning"
tags: [world-ai, fine-tuning]
aliases: [prefix-tuning]
---

Prepend trainable key/value vectors to every layer's attention, freezing the base model.

Prefix tuning learns task-specific key/value 'prefixes' injected into each attention layer while the model stays frozen. It is more expressive than input-only prompt tuning because it influences every layer, and remains parameter-efficient.

**Example:** Each task ships a small set of per-layer prefixes rather than a full fine-tuned copy.

## Related

- [[prompt-tuning]]
- [[peft]]
- [[lora]]
- [[attention]]

Source: authored
