---
title: "Rejection-Sampling Fine-Tuning"
tags: [world-ai, fine-tuning]
aliases: [rejection-sampling-finetuning, RFT, best-of-N distillation]
---

Sample many answers, keep only the ones that pass a check, then fine-tune on the survivors.

Rejection-sampling fine-tuning generates many candidate completions per prompt, filters them with a verifier, reward model, or ground-truth check, and trains the model on the accepted ones. It is a simple, stable alternative to RL for self-improvement and underpins much self-distillation.

**Example:** For each math problem the model draws 16 solutions, keeps those whose final answer is verified correct, and fine-tunes on that filtered set.

## Related

- [[self-distillation]]
- [[verifier]]
- [[raft]]
- [[sft]]
- [[reward-model]]

Source: authored
