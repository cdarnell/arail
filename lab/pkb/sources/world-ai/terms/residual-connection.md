---
title: "Residual Connection"
tags: [world-ai, architecture]
aliases: [residual-connection, skip connection]
---

Add a layer's input to its output so gradients and signal can flow straight through deep stacks.

A residual (skip) connection routes a sublayer's input around it and adds it back to the output, so each block learns a delta on top of identity. This keeps gradients from vanishing in very deep networks and is, with layer normalization, what makes 100+-layer transformers trainable.

**Example:** Each transformer block computes x + Attention(x) and x + FFN(x), never replacing x outright.

## Related

- [[transformer]]
- [[layernorm]]
- [[backprop]]
- [[gradient]]

Source: authored
