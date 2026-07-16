---
title: "Inference"
tags: [world-ai, fundamentals]
aliases: [inference, serving]
---

Running a trained model to produce outputs — the deployment side, as opposed to training.

Inference is using a trained model to generate predictions for real inputs. For LLMs it is autoregressive: produce one token, append it, repeat. Latency, throughput, and memory (the KV-cache) are the central concerns, distinct from the one-time cost of training.

**Example:** Typing a prompt into a chatbot and watching tokens stream back is inference; the KV-cache and sampling settings shape its speed and style.

## Related

- [[kv-cache]]
- [[speculative-decoding]]
- [[temperature]]
- [[vllm]]
- [[prompt-caching]]

Source: authored
