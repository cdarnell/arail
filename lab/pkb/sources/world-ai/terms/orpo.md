---
title: "ORPO"
tags: [world-ai, rl-alignment]
aliases: [orpo, Odds Ratio Preference Optimization]
---

A single-stage method that combines instruction tuning and preference alignment without a separate reward model or reference model.

Odds Ratio Preference Optimization folds preference alignment into SFT by adding an odds-ratio penalty on dispreferred responses, removing the need for a separate reward model and reference model. It simplifies the alignment pipeline into one stage.

**Example:** ORPO fine-tunes and aligns in one pass, skipping the usual SFT-then-DPO two-step.

## Related

- [[dpo]]
- [[ipo]]
- [[kto]]
- [[sft]]
- [[reward-model]]

Source: authored
