---
title: "Instruction Tuning"
tags: [world-ai, fine-tuning]
aliases: [instruction-tuning]
---

Fine-tune a base model on instruction-response pairs so it follows natural-language commands.

Instruction tuning is the SFT stage that turns a raw next-token base model into an assistant by training on many (instruction, good response) pairs across diverse tasks. It teaches the model to follow directions and generalize to unseen instructions before any alignment step.

**Example:** After instruction tuning, 'summarize this in two lines' reliably yields a two-line summary.

## Related

- [[sft]]
- [[fine-tune]]
- [[zero-shot]]
- [[rlhf]]

Source: authored
