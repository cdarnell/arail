---
title: "Self-Distillation"
tags: [world-ai, fine-tuning]
aliases: [self-distillation, self-training, model as its own teacher]
---

A model acts as its own teacher — its current outputs become training targets for a refined version of itself.

Self-distillation removes the separate large teacher: the model generates its own outputs, reasoning traces, or soft labels and then trains on the best of them, so a single network bootstraps a sharper copy of itself. Variants filter generations by a reward or verifier (keep only correct traces) or distill an ensemble of the model's own sampled answers back into its weights. It is how a model can keep improving without a bigger model to copy from.

**Example:** A student samples several chain-of-thought answers, keeps only the ones that reach the verified answer, and fine-tunes on those — lifting its own accuracy with no external teacher.

## Related

- [[distillation]]
- [[teacher]]
- [[student]]
- [[scotd]]
- [[convergence]]

Source: authored
