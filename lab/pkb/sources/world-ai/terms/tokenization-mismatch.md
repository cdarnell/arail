---
title: "Tokenization mismatch"
tags: [world-ai, pathologies]
aliases: [tokenization-mismatch]
---

Tokenizer and model are mismatched — inputs are decoded/encoded incorrectly.

A tokenization mismatch occurs when the tokenizer used during training differs from the one used during inference, or when a tokenizer is applied to data outside its vocabulary distribution. Symptoms range from subtle (degraded performance on certain token sequences) to severe (completely corrupted outputs). Always use the tokenizer shipped with the model checkpoint and apply it consistently across train/val/test.

**Example:** Loading a LLaMA-2 checkpoint but tokenizing with the GPT-2 tokenizer produces nonsensical outputs because the token-id spaces are completely different.

## Related

- [[data-leakage]]
- [[stale-mismatched-checkpoint]]

Source: HF Transformers tokenizer docs (AutoTokenizer.from_pretrained); OLMo tokenizer documentation
