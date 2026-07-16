---
title: "Byte-Pair Encoding"
tags: [world-ai, architecture]
aliases: [bpe, BPE]
---

A subword tokenization that iteratively merges the most frequent character pairs into tokens.

Byte-Pair Encoding builds a vocabulary by starting from characters/bytes and repeatedly merging the most frequent adjacent pair, yielding tokens that range from characters to whole words. It balances vocabulary size against sequence length and handles unseen words gracefully by falling back to subwords.

**Example:** BPE splits 'tokenization' into known pieces like 'token' + 'ization' rather than failing on the whole word.

## Related

- [[tokenizer]]
- [[sentencepiece]]
- [[vocabulary]]

Source: authored
