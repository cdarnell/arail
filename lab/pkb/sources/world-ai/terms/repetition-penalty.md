---
title: "Repetition Penalty"
tags: [world-ai, inference]
aliases: [repetition-penalty, frequency penalty, presence penalty]
---

A decoding adjustment that lowers the probability of tokens already generated, reducing loops.

Repetition (and the related frequency/presence) penalties down-weight tokens that have already appeared, discouraging the model from looping or echoing itself. They are post-logit adjustments applied at sampling time, tuned to avoid both repetition and unnatural avoidance.

**Example:** A mild repetition penalty stops a model from chanting the same phrase over and over.

## Related

- [[sampling]]
- [[temperature]]
- [[top-p]]
- [[greedy-decoding]]

Source: authored
