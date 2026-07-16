---
title: "Catastrophic Forgetting"
tags: [world-ai, training]
aliases: [catastrophic-forgetting, forgetting]
---

When fine-tuning on a new task erases capabilities the model previously had.

Catastrophic forgetting is the tendency of a network to overwrite old knowledge when trained on new data, because the same weights encode everything. It is why aggressive fine-tuning can wreck general ability, and why PEFT, rehearsal, and model merging are used to preserve it.

**Example:** Fine-tuning hard on legal text makes the model worse at everyday chat — it forgot.

## Related

- [[fine-tune]]
- [[peft]]
- [[domain-adaptation]]
- [[model-merging]]

Source: authored
