---
title: "Autoencoder"
tags: [world-ai, architecture]
aliases: [autoencoder]
---

Encoder-decoder trained to reconstruct its own input — learns a compressed representation.

An autoencoder trains an encoder (maps input to a lower-dimensional latent code) and a decoder (reconstructs the input from the code) by minimizing reconstruction loss. The bottleneck forces the model to learn a compact, meaningful representation. Used for dimensionality reduction, denoising, and as a component in generative models (VAE) and tokenizers for image generation (VQ-VAE).

**Example:** A denoising autoencoder trained on corrupted text learns to reconstruct clean text, building a robust internal representation of language.

## Related

- [[variational-autoencoder]]

Source: Goodfellow et al. — Deep Learning ch.14 (autoencoders)
