---
title: "Distribution shift"
tags: [world-ai, conditions]
aliases: [distribution-shift]
---

Training and deployment data have different distributions — model degrades at inference.

When the statistical distribution of inputs at deployment differs from the training distribution, model performance degrades. Types include covariate shift (input distribution changes), label shift (output distribution changes), and dataset shift (both). Common in fine-tuning: a model trained on one domain's text degrades on another. Continued pretraining on the target domain mitigates this.

**Example:** A model fine-tuned on scientific papers degrades when deployed on casual user queries because the writing style and vocabulary distribution differ.

## Related

- [[continued-pretraining]]
- [[data-leakage]]
- [[train-val-loss-gap]]

Source: Goodfellow et al. — Deep Learning ch.7; HF docs on domain adaptation
