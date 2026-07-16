---
title: "Posterior collapse"
tags: [world-ai, conditions]
aliases: [posterior-collapse]
---

VAE latent variables collapse to the prior — the encoder becomes useless.

In variational autoencoders (VAEs), posterior collapse occurs when the decoder learns to ignore the latent code entirely, generating outputs from the prior alone. The KL divergence term in the ELBO objective drives the posterior toward the prior, and if the decoder is expressive enough, it learns to do without the latent information. Addressed by KL annealing, free bits, or beta-VAE weighting.

**Example:** A VAE for text generation trains with near-zero KL divergence throughout — the decoder generates text from the prior, ignoring the encoder; interpolations in latent space produce no meaningful variation.

## Related

- [[mode-collapse]]
- [[variational-autoencoder]]

Source: Bowman et al. (2016) — Generating Sentences from a Continuous Space (posterior collapse identification); Goodfellow et al. — Deep Learning ch.20
