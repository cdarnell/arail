---
title: "TGI"
tags: [world-ai, formats-runtime]
aliases: [tgi, Text Generation Inference]
---

Hugging Face's production inference server for high-throughput, low-latency LLM serving.

Text Generation Inference is a serving stack with continuous batching, tensor parallelism, and optimized kernels for deploying LLMs at scale, comparable in role to vLLM. It exposes a standard generation API.

**Example:** TGI serves a model to many concurrent users with continuous batching and paged attention.

## Related

- [[vllm]]
- [[tensorrt]]
- [[continuous-batching]]
- [[huggingface]]

Source: authored
