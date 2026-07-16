---
title: "Task Arithmetic"
tags: [world-ai, fine-tuning]
aliases: [task-arithmetic]
---

Treat the weight change from fine-tuning as a 'task vector' you can add or subtract.

Task arithmetic defines a task vector as fine-tuned-minus-base weights; adding it imparts the skill, subtracting it removes a behavior, and summing vectors composes skills. It is the conceptual basis for several merging methods.

**Example:** Subtracting a 'toxicity' task vector from a model reduces that behavior without retraining.

## Related

- [[model-merging]]
- [[ties-merging]]
- [[fine-tune]]

Source: authored
