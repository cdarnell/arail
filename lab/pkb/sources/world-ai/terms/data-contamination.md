---
title: "Data Contamination"
tags: [world-ai, training]
aliases: [data-contamination]
---

When benchmark or test data leaks into training, inflating scores and invalidating the eval.

Data contamination happens when evaluation examples (or near-duplicates) appear in the training corpus, so high scores reflect memorization rather than ability. It is a serious threat to benchmark validity given web-scale training data, and is checked with n-gram overlap and canary strings.

**Example:** A model 'acing' a benchmark whose questions were scraped into its training data is contaminated, not capable.

## Related

- [[benchmark]]
- [[eval]]
- [[ngram]]
- [[generalization]]

Source: authored
