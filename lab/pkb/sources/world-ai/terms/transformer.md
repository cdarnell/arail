---
title: "Transformer"
tags: [world-ai, architecture]
aliases: [transformer, transformer architecture]
---

The attention-based neural architecture behind essentially every modern LLM.

The transformer stacks blocks of multi-head attention and feed-forward layers with residual connections and normalization, processing all tokens in parallel. Introduced in 'Attention Is All You Need' (2017), it scales beautifully and underpins GPT, Llama, and the rest.

**Example:** A 7B decoder-only transformer is about 32 such blocks; depth and width set the parameter count.

## Related

- [[attention]]
- [[moe]]
- [[layernorm]]
- [[rope]]

Source: authored
