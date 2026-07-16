---
title: "Small language model (SLM)"
tags: [world-ai, fine-tuning]
aliases: [small-language-model]
---

A language model small enough to run on consumer hardware — typically 1B–13B parameters.

Small language models (1B–13B parameters) are the frontier of consumer-hardware deployment: they run at useful token rates on M-series Apple Silicon and fit in 8–24GB VRAM. SLMs trained on a specialized domain (via fine-tuning + distillation) can outperform much larger general models in that domain, because domain depth compensates for reduced overall capacity.

**Example:** A 7B model fine-tuned on domain-specific data can answer domain questions more reliably than a 70B generalist, while fitting on a single consumer GPU.

## Related

- [[knowledge-distillation]]
- [[quantization]]
- [[domain-specialist-model]]

Source: Goodfellow et al. — Deep Learning (model compression); HF model hub SLM examples; NVIDIA deep-learning performance guide
