---
title: "Add gradient clipping"
tags: [world-ai, care-actions]
aliases: [add-gradient-clipping]
---

Cap gradient norms before the optimizer step to prevent destabilizing updates.

Gradient clipping rescales the gradient vector so its L2 norm does not exceed a threshold (commonly 1.0), preventing any single step from making a catastrophically large parameter update. It is the standard defense against exploding gradients in deep or recurrent models. In PyTorch, applied via `torch.nn.utils.clip_grad_norm_(parameters, max_norm=1.0)` before `optimizer.step()`.

**Example:** Adding `max_grad_norm=1.0` to HF Trainer prevents the gradient norm spikes that produced loss spikes in the baseline run.

## Related

- [[exploding-gradients]]
- [[diverging-loss]]
- [[gradient-clipping]]

Source: PyTorch torch.nn.utils.clip_grad_norm_ docs; HF Trainer (max_grad_norm); Goodfellow et al. — Deep Learning §10.11
