---
title: "Noisy labels"
tags: [world-ai, pathologies]
aliases: [noisy-labels]
---

Training data contains incorrectly labeled examples — the model learns corrupted signal.

Label noise means some fraction of training examples have incorrect ground-truth labels. The model attempts to fit these incorrect labels, wasting capacity and potentially degrading generalization. In instruction tuning, low-quality completions act as noisy labels. Label smoothing provides a partial defense by preventing the model from fitting labels with full confidence.

**Example:** A text classification dataset scraped from the web has 8% mislabeled examples; the model's val accuracy plateaus 4 points below a clean-data baseline.

## Related

- [[class-imbalance]]
- [[data-leakage]]
- [[duplicate-contaminated-data]]

Source: Goodfellow et al. — Deep Learning ch.7 (regularization against label noise); HF datasets quality guides
