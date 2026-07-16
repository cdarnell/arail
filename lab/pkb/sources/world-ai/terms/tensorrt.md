---
title: "TensorRT"
tags: [world-ai, formats-runtime]
aliases: [tensorrt, TensorRT-LLM]
---

NVIDIA's inference optimizer/runtime that compiles models into highly tuned GPU engines.

TensorRT compiles a model into a hardware-specific engine with fused kernels, quantization, and kernel auto-tuning for maximum GPU inference throughput and low latency. TensorRT-LLM specializes it for transformers.

**Example:** Compiling a model with TensorRT-LLM yields a fast, fused engine tuned for the target GPU.

## Related

- [[onnx]]
- [[cuda]]
- [[kernel-fusion]]
- [[vllm]]
- [[tgi]]

Source: authored
