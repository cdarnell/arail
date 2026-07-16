---
title: "Speculative Decoding"
tags: [world-ai, performance]
aliases: [speculative-decoding, speculative sampling, spec decode]
---

A small draft model proposes several tokens; the big model verifies them in one pass — lossless speedup.

Speculative decoding runs a cheap draft model to guess the next few tokens, then the large target model verifies them all in a single forward pass, accepting the longest correct prefix. Output is identical to normal decoding, but throughput rises 2-3x because the expensive model runs less often.

**Example:** The draft proposes 5 tokens, the target accepts the first 4 and corrects the 5th — 4 tokens produced for roughly one big-model step.

## Related

- [[kv-cache]]
- [[inference]]
- [[vllm]]
- [[layer-streaming]]

Source: knowledge_base/wiki/concepts/speculative-decoding.md
