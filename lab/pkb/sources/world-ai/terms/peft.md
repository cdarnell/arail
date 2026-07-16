---
title: "PEFT"
tags: [world-ai, fine-tuning]
aliases: [peft, Parameter-Efficient Fine-Tuning]
---

An umbrella for methods (LoRA, adapters, prefix-tuning) that tune a tiny fraction of parameters.

PEFT covers techniques that adapt a model by training only a small set of new or selected parameters while freezing the rest — LoRA, adapters, prefix/prompt tuning, and more. It is also the name of Hugging Face's library implementing them.

**Example:** Using the PEFT library, you wrap a base model with a LoRA config and train under 1% of its parameters.

## Related

- [[lora]]
- [[qlora]]
- [[adapters]]

Source: authored
