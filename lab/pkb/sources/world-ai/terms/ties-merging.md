---
title: "TIES-Merging"
tags: [world-ai, fine-tuning]
aliases: [ties-merging, TIES]
---

A merge recipe that trims small changes and resolves sign conflicts between task vectors.

TIES-Merging improves naive averaging by keeping only the largest-magnitude parameter changes, electing a consistent sign per parameter across models, and then averaging the agreeing updates. Resolving interference yields merged models that retain more of each source's skill.

**Example:** TIES merges three fine-tunes with fewer destructive conflicts than plain weight averaging.

## Related

- [[model-merging]]
- [[task-arithmetic]]
- [[fine-tune]]

Source: authored
