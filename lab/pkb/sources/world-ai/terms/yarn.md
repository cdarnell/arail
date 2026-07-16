---
title: "YaRN"
tags: [world-ai, architecture]
aliases: [yarn, YaRN context extension]
---

A method to extend a model's usable context window by rescaling its rotary position frequencies.

YaRN (Yet another RoPE extensioN) interpolates and rescales RoPE frequencies, often with brief fine-tuning, so a model trained at one context length works well at a much longer one. It is a common way to stretch context windows without full retraining.

**Example:** YaRN extends a 4k-context model to 32k with a short fine-tune rather than pretraining anew.

## Related

- [[rope]]
- [[positional-encoding]]
- [[context-window]]

Source: authored
