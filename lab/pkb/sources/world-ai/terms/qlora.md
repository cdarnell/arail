---
title: "QLoRA"
tags: [world-ai, fine-tuning]
aliases: [qlora, Quantized LoRA]
---

LoRA on top of a 4-bit quantized base model — fine-tune big models on one consumer GPU.

QLoRA quantizes the frozen base to 4-bit (NF4) to shrink its footprint, then trains LoRA adapters on top in higher precision, with gradients flowing through the quantized weights via dequant-on-the-fly. Near-full-fine-tune quality at a fraction of the VRAM.

**Example:** QLoRA made it possible to fine-tune a 65B model on a single 48GB GPU — previously impossible without multiple A100s.

## Related

- [[lora]]
- [[quantization]]
- [[int4]]
- [[peft]]

Source: authored
