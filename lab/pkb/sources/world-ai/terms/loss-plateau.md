---
title: "Loss plateau"
tags: [world-ai, symptoms]
aliases: [loss-plateau]
---

Loss stops improving for many steps — training is stalled.

A plateau means the optimizer is stuck: the learning rate may be too low to escape a saddle point or local minimum, the schedule may have decayed too aggressively, the data may be exhausted, or the model has no more capacity. It differs from convergence (which is intentional) by occurring earlier than expected and being confirmed by no improvement on held-out loss.

**Example:** Training loss flatlines at 2.6 from step 15k to 25k with no improvement; the model has not reached its target perplexity.

## Related

- [[learning-rate-too-low]]
- [[slow-convergence]]
- [[learning-rate-schedule]]
- [[switch-optimizer]]

Source: Goodfellow, Bengio & Courville — Deep Learning ch.8; HF Trainer docs (lr_scheduler_type)
