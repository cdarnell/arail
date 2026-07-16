---
title: "Mixed-precision training"
tags: [world-ai, training]
aliases: [mixed-precision-training]
---

Use fp16 or bf16 for forward/backward passes while keeping fp32 master weights.

Mixed-precision training stores model weights as fp32 (master copy) but performs forward and backward passes in fp16 or bf16. This approximately halves memory footprint for activations and tensors, and speeds up compute on hardware with fp16/bf16 tensor cores. fp16 requires a loss scaler (GradScaler) to avoid underflow; bf16 does not (wider dynamic range). Most modern GPU fine-tuning uses bf16 or fp16 with AMP.

**Example:** Setting `fp16=True` in HF Trainer enables PyTorch AMP with a GradScaler; `bf16=True` uses bf16 without scaling, preferred on Ampere+ GPUs.

## Related

- [[out-of-memory-error]]
- [[nan-loss]]
- [[fp16-overflow]]
- [[batch-size]]

Source: PyTorch AMP docs (torch.cuda.amp); NVIDIA mixed-precision training guide; HF Trainer docs (fp16, bf16)
