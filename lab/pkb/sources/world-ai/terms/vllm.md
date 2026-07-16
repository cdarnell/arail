---
title: "vLLM"
tags: [world-ai, inference]
aliases: [vllm, vLLM]
---

A high-throughput LLM serving engine; its PagedAttention manages the KV-cache like virtual memory.

vLLM maximizes GPU throughput via PagedAttention — treating the KV-cache as paged memory to eliminate fragmentation — plus continuous batching of incoming requests. It is the enterprise-grade backend for serving teacher models on GPUs.

**Example:** QuKaiZen uses vLLM (TEACHER_BACKEND=vllm) to serve teachers on H100s with continuous batching and FP8.

## Related

- [[kv-cache]]
- [[inference]]
- [[flashattention]]

Source: qukaizen/docs/TECHNIQUES.md
