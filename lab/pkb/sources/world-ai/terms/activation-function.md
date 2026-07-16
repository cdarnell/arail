---
title: "Activation Function"
tags: [world-ai, fundamentals]
aliases: [activation-function, nonlinearity]
---

The nonlinear function applied to neuron outputs, letting networks model more than straight lines.

An activation function applies a nonlinearity to a layer's outputs; without it, stacked linear layers collapse into a single linear map. Modern transformers favor smooth gated variants (GELU, SwiGLU) over older ReLU for better gradients and quality. The choice sits inside the feed-forward block.

**Example:** Swapping ReLU for a gated SwiGLU activation in the FFN typically nudges model quality up at equal size.

## Related

- [[gelu]]
- [[feedforward-network]]
- [[transformer]]
- [[hidden-state]]

Source: authored
