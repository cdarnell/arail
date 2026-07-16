---
title: "Dead neurons"
tags: [world-ai, conditions]
aliases: [dead-neurons]
---

ReLU units stuck at zero — never activate, never learn.

A 'dead' ReLU neuron is one whose pre-activation is always negative, so it always outputs zero and receives no gradient. Once dead, the neuron cannot recover without reinitialization. Dead neurons reduce the effective capacity of the network. Caused by large negative weight initializations or by large learning rates that push weights into the negative region. Mitigated by using GELU or Leaky ReLU activations, or by careful initialization.

**Example:** After training, 30% of the ReLU units in a hidden layer have zero output on all validation inputs — the network has effectively lost that capacity.

## Related

- [[vanishing-gradients]]
- [[relu]]
- [[gelu]]
- [[weight-initialization]]

Source: Goodfellow et al. — Deep Learning §6.3.1 (ReLU and variants); PyTorch activation docs
