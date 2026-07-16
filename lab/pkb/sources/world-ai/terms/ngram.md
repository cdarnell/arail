---
title: "N-gram"
tags: [world-ai, fundamentals]
aliases: [ngram]
---

A contiguous sequence of n tokens; the basis of pre-neural language models and still used for metrics.

An n-gram is a run of n consecutive tokens (bigram = 2, trigram = 3). Classic language models estimated the probability of the next token from n-gram counts. Today n-grams persist in evaluation metrics (BLEU, ROUGE) and in detecting training-data overlap.

**Example:** A trigram model predicts the next word from the previous two; 'the cat ___' favors 'sat'.

## Related

- [[tokenizer]]
- [[perplexity]]
- [[data-contamination]]

Source: authored
