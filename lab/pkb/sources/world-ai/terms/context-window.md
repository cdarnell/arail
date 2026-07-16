---
title: "Context Window"
tags: [world-ai, architecture]
aliases: [context-window, context length]
---

The maximum number of tokens a model can attend to at once — its working span of input plus output.

The context window is the hard cap on how many tokens (prompt + generated output) a model can process in a single pass. Everything outside it is invisible to the model, which is why long documents are chunked and agents need external memory. Larger windows cost more compute and KV-cache memory, roughly with length.

**Example:** A 128k-token window fits a short book; a 600-page manual must still be split or retrieved against.

## Related

- [[kv-cache]]
- [[rag]]
- [[long-term-memory]]
- [[tokenizer]]
- [[sliding-window-attention]]

Source: authored
