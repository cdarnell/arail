---
title: "Mode collapse"
tags: [world-ai, conditions]
aliases: [mode-collapse]
---

Generator produces only a few outputs — diversity collapses.

In generative models (GANs, VAEs, certain RL fine-tuning setups), mode collapse is when the model learns to generate a narrow subset of valid outputs. The discriminator or reward model can be fooled by the same outputs repeatedly. In GAN training, the generator finds a 'safe' mode that always fools the discriminator and stops exploring. In RLHF, reward hacking produces similar behavior — the model finds a narrow pattern that maximizes reward without being generally helpful.

**Example:** A GAN trained on face images produces only three distinct face shapes after training; all generated images look nearly identical.

## Related

- [[generative-adversarial-network]]
- [[posterior-collapse]]
- [[rlhf]]

Source: Goodfellow et al. — Deep Learning ch.20 (generative models, GANs); RLHF literature (reward hacking)
