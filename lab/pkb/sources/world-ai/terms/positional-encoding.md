---
title: "Positional Encoding"
tags: [world-ai, architecture]
aliases: [positional-encoding, position embeddings]
---

Information added to tokens so the otherwise order-blind transformer knows their sequence positions.

Attention is permutation-invariant — it sees a bag of tokens — so models inject position information via positional encodings: fixed sinusoids, learned embeddings, or rotary methods (RoPE) that rotate query/key vectors by position. The choice strongly affects how well a model extrapolates to longer contexts than it trained on.

**Example:** Without positional encoding, 'dog bites man' and 'man bites dog' would look identical to the model.

## Related

- [[rope]]
- [[attention]]
- [[transformer]]
- [[context-window]]

Source: authored
