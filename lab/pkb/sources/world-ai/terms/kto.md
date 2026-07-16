---
title: "KTO"
tags: [world-ai, rl-alignment]
aliases: [kto, Kahneman-Tversky Optimization]
---

Preference alignment from simple good/bad labels rather than paired comparisons.

Kahneman-Tversky Optimization aligns a model using per-example binary signals (this output was desirable or not) instead of A-vs-B pairs, drawing on prospect theory. It eases data collection since you needn't produce matched pairs.

**Example:** KTO trains on a pile of individually thumbs-up/thumbs-down responses, no pairing required.

## Related

- [[dpo]]
- [[ipo]]
- [[orpo]]
- [[preference-data]]

Source: authored
