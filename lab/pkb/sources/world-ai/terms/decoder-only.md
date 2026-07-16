---
title: "Decoder-Only"
tags: [world-ai, architecture]
aliases: [decoder-only, causal LM]
---

The autoregressive transformer design used by most LLMs: predict the next token, attending only to the past.

A decoder-only model uses causal (masked) self-attention so each position can attend only to earlier tokens, and is trained to predict the next token. This single-stack design — no separate encoder — is what nearly all modern generative LLMs use, scaling cleanly and unifying understanding and generation in one objective.

**Example:** Generating text, the model emits one token, appends it, and predicts the next, never peeking ahead.

## Related

- [[transformer]]
- [[encoder-decoder]]
- [[attention]]
- [[llm]]

Source: authored
