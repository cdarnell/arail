---
title: "Model Merging"
tags: [world-ai, fine-tuning]
aliases: [model-merging]
---

Combine multiple fine-tuned models into one by arithmetic on their weights, no extra training.

Model merging blends the weights of several models (often fine-tunes of a shared base) into a single model that inherits multiple skills, using averaging, SLERP, or task-vector arithmetic. It is a cheap way to fuse capabilities and mitigate catastrophic forgetting.

**Example:** Averaging a 'code' fine-tune and a 'chat' fine-tune of the same base yields one model decent at both.

## Related

- [[task-arithmetic]]
- [[ties-merging]]
- [[fine-tune]]
- [[catastrophic-forgetting]]

Source: authored
