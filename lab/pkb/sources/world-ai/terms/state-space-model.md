---
title: "State-Space Model"
tags: [world-ai, architecture]
aliases: [state-space-model, SSM, Mamba]
---

A sequence architecture that carries a recurrent hidden state, scaling linearly with length instead of attention's quadratic cost.

State-space models (and selective variants like Mamba) process sequences with a continuous-time-inspired recurrence: a compact hidden state is updated token by token, giving linear-time, constant-memory inference over long sequences. Selective SSMs make the state update input-dependent, recovering much of attention's content-routing ability without its quadratic blow-up.

**Example:** Streaming a million-token log, an SSM keeps a fixed-size state rather than a KV-cache that grows with every token.

## Related

- [[transformer]]
- [[attention]]
- [[kv-cache]]
- [[context-window]]

Source: authored
