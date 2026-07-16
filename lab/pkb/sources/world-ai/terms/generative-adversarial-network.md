---
title: "Generative adversarial network (GAN)"
tags: [world-ai, architecture]
aliases: [generative-adversarial-network]
---

Generator and discriminator trained adversarially — generator fools the discriminator.

A GAN (Goodfellow et al., 2014) consists of a generator (G) that produces samples from noise and a discriminator (D) that tries to distinguish real from generated samples. G is trained to fool D; D is trained to distinguish. The adversarial dynamic produces sharp, high-quality samples in well-designed architectures. Mode collapse (G finds a few samples that always fool D) is the canonical failure mode. Largely superseded by diffusion models for image generation.

**Example:** A face-generation GAN produces photorealistic images; after mode collapse, it produces only a few face types regardless of the noise input.

## Related

- [[mode-collapse]]
- [[variational-autoencoder]]

Source: Goodfellow et al. — Generative Adversarial Networks arXiv:1406.2661; Goodfellow et al. — Deep Learning ch.20
