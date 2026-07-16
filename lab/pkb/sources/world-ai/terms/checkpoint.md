---
title: "Checkpoint"
tags: [world-ai, training]
aliases: [checkpoint, model checkpoint]
---

A saved snapshot of model weights (and often optimizer state) you can resume or deploy from.

A checkpoint persists the model's parameters — and during training, the optimizer state and step — so a run can resume after interruption or a version can be evaluated and shipped. Modern checkpoints use safetensors for safe, fast loading.

**Example:** Saving a checkpoint every 500 steps means a crash at step 1700 resumes from 1500, not from scratch.

## Related

- [[safetensors]]
- [[gguf]]
- [[fsdp]]

Source: authored
