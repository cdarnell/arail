---
title: "GGUF"
tags: [world-ai, formats-runtime]
aliases: [gguf, GGML successor]
---

A single-file binary format for quantized models, built for fast local inference (llama.cpp).

GGUF packs weights (usually quantized), tokenizer, and metadata into one memory-mappable file so a model loads fast and runs on commodity hardware. It is the format used by llama.cpp and friends, superseding the older GGML format.

**Example:** llama-2-7b.Q4_K_M.gguf is a 7B model quantized to ~4-bit (~4GB) that runs on a laptop with llama.cpp.

## Related

- [[quantization]]
- [[int4]]
- [[safetensors]]
- [[inference]]

Source: authored
