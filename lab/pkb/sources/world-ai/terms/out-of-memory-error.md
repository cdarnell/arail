---
title: "Out-of-memory (OOM) error"
tags: [world-ai, symptoms]
aliases: [out-of-memory-error]
---

GPU runs out of VRAM — the process crashes with a CUDA OOM.

A CUDA out-of-memory error means the model, activations, gradients, and optimizer states together exceed the available GPU VRAM. OOM can be triggered by a large batch, a large sequence length, or optimizer states (Adam keeps 2 extra fp32 copies per parameter). Solutions involve reducing batch size, using gradient accumulation to maintain effective batch size, or switching to more memory-efficient training (mixed precision, gradient checkpointing).

**Example:** Training a 7B model with batch_size=8 and seq_len=2048 in fp32 triggers OOM on a 24GB GPU; switching to bf16 + gradient_accumulation_steps=4 with batch_size=2 fits the same effective batch.

## Related

- [[batch-size]]
- [[mixed-precision-training]]
- [[gradient-accumulation]]
- [[increase-batch-size]]

Source: PyTorch memory docs; HF Trainer docs (fp16, gradient_accumulation_steps); NVIDIA deep-learning performance guide
