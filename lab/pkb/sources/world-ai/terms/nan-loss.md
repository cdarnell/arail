---
title: "NaN loss"
tags: [world-ai, symptoms]
aliases: [nan-loss]
---

Loss value becomes Not-a-Number — the run is numerically broken.

A NaN in the loss typically means a numerical overflow or a division by zero somewhere in the forward pass or loss computation. In fp16/bf16 mixed-precision training this commonly traces to a loss scale overflow. Once a NaN propagates into gradients, the optimizer corrupts model weights and the run must be restored from a last-good checkpoint.

**Example:** Loss prints 'nan' at step 2100 after the GradScaler grew the loss scale too large; rolling back to step 2000 and reducing the initial scale clears it.

## Related

- [[fp16-overflow]]
- [[numerical-overflow]]
- [[diverging-loss]]
- [[resume-from-checkpoint]]

Source: PyTorch AMP / GradScaler docs (pytorch.org/docs/stable/amp.html); NVIDIA mixed-precision guide
