---
title: "Gradient noise"
tags: [world-ai, pathologies]
aliases: [gradient-noise]
---

High-variance gradient estimates slow convergence and require larger batches or LR tuning.

Stochastic gradient descent introduces gradient noise because each mini-batch is a sample of the full dataset gradient. At small batch sizes, this noise is high and limits the effective LR (linear scaling rule: halve the batch → halve the LR to keep stability). Data corruption, noisy labels, and large LR all amplify gradient noise. Gradient clipping and larger batches reduce its impact.

**Example:** Training with batch_size=4 on a noisy web corpus produces high gradient variance; loss curves are jagged and final performance is 2 points below the batch_size=128 baseline.

## Related

- [[noisy-labels]]
- [[exploding-gradients]]
- [[add-gradient-clipping]]
- [[batch-size]]

Source: Goodfellow et al. — Deep Learning ch.8; Karpathy nanoGPT notes
