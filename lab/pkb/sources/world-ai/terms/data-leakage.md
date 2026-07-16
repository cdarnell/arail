---
title: "Data leakage"
tags: [world-ai, conditions]
aliases: [data-leakage]
---

Validation/test data has leaked into training — metrics are invalid.

Data leakage occurs when information from the validation or test split is visible during training, either through preprocessing that uses the full dataset (normalization statistics, tokenizer training) or through contaminated splits. The model learns to exploit the leaked information and achieves artificially high validation metrics that do not reflect real-world performance.

**Example:** A tokenizer trained on the combined train+val+test set learns vocabulary statistics from the val split — any model using it has technically seen val data.

## Related

- [[duplicate-contaminated-data]]
- [[train-val-loss-gap]]
- [[tokenization-mismatch]]

Source: Goodfellow et al. — Deep Learning ch.5 (evaluation); HF datasets docs (train/test split)
