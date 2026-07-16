---
title: "Duplicate / contaminated data"
tags: [world-ai, pathologies]
aliases: [duplicate-contaminated-data]
---

Training data contains repeated or benchmark-contaminated examples.

Duplicate training examples cause the model to see certain patterns disproportionately, biasing the learned distribution. Contamination from benchmark or test data gives the model unfair advantage on evaluation and makes training metrics misleading. Large web-scraped corpora commonly have >10% duplication before deduplication. MinHash / n-gram deduplication is standard practice.

**Example:** A pretraining corpus before deduplication has the Wikipedia dump repeated 4× across different crawl snapshots; the model over-represents encyclopedic text.

## Related

- [[data-leakage]]
- [[loss-spike]]
- [[noisy-labels]]

Source: Lee et al. (2022) — Deduplicating Training Data Makes Language Models Better; OLMo data pipeline docs
