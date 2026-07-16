---
title: "Experiment"
tags: [world-ai, fundamentals]
aliases: [experiment, experimentation, training run]
---

A single tracked training or evaluation run with a fixed configuration, used to test one change against a baseline.

An experiment isolates one variable — a hyperparameter, a data change, an architecture tweak — and measures its effect against a baseline under otherwise identical conditions. Each run logs its config, metrics, and artifacts so results are reproducible and comparable. In ARAIL, autoresearch agents run experiments continuously and score each against evolving rubrics — what gets measured gets improved.

**Example:** Change only the learning rate from 2e-4 to 1e-4, rerun training, and compare validation loss to the baseline; if it improves and nothing else changed, the experiment isolated the cause.

## Related

- [[checkpoint]]
- [[perplexity]]

Source: authored
