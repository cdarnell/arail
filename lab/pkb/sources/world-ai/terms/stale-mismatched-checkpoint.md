---
title: "Stale / mismatched checkpoint"
tags: [world-ai, pathologies]
aliases: [stale-mismatched-checkpoint]
---

Loading a checkpoint whose architecture or tokenizer does not match the current code.

A stale checkpoint is saved from a different model version (different architecture, layer names, or config) than the one being loaded. Shape mismatches cause hard errors; silent mismatches (different normalization, different positional encoding) cause degraded performance. Always pin the model architecture version alongside the checkpoint and use `from_pretrained` with the matching config.

**Example:** Loading a checkpoint saved before a positional encoding change into the post-change architecture silently loads misaligned weights; the model under-performs the baseline without any error.

## Related

- [[tokenization-mismatch]]
- [[resume-from-checkpoint]]
- [[checkpoint]]

Source: HF Transformers docs (from_pretrained, config matching); OLMo checkpoint management docs
