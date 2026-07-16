---
title: "Exploding gradients"
tags: [world-ai, symptoms]
aliases: [exploding-gradients]
---

Gradient norms spike to very large values, destabilizing updates.

When gradients grow exponentially through deep or recurrent layers, parameter updates become destructively large, driving the loss toward divergence. Observable by logging gradient norms: a healthy run keeps them bounded; exploding gradients produce norm values orders of magnitude above baseline. The standard intervention is gradient clipping.

**Example:** Gradient norm logs show a jump from ~1.0 to >100 at step 3k, coinciding with a loss spike; gradient clipping (max_norm=1.0) prevents the destabilization.

## Related

- [[diverging-loss]]
- [[learning-rate-too-high]]
- [[add-gradient-clipping]]
- [[gradient-clipping]]

Source: Goodfellow et al. — Deep Learning §10.7 (gradient clipping); PyTorch torch.nn.utils.clip_grad_norm_ docs
