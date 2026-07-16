---
title: "Adapter layers"
tags: [world-ai, fine-tuning]
aliases: [adapter-layers]
---

Small bottleneck modules inserted into transformer layers — trained while base model is frozen.

Adapter layers (Houlsby et al., 2019) insert small two-layer bottleneck modules (down-project → nonlinearity → up-project) inside each transformer layer. Only adapter parameters are trained during fine-tuning; the base model is frozen. This enables multi-task fine-tuning by swapping adapter sets and is a PEFT method. LoRA has largely superseded adapters for LLM fine-tuning but adapters remain common in multi-modal and multi-task settings.

**Example:** Inserting adapter layers after the FFN in each of 32 transformer layers adds ~10M parameters (bottleneck dim=64) vs. 7B frozen base parameters — 0.14% of total.

## Related

- [[peft]]
- [[lora]]
- [[fine-tuning]]

Source: Houlsby et al. — Parameter-Efficient Transfer Learning arXiv:1902.00751; HF peft docs (AdapterConfig)
