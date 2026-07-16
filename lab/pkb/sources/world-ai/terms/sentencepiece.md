---
title: "SentencePiece"
tags: [world-ai, formats-runtime]
aliases: [sentencepiece]
---

A language-agnostic tokenizer toolkit that trains subword models directly on raw text.

SentencePiece tokenizes raw text without pre-tokenizing on whitespace, treating the input as a stream of Unicode and learning BPE or unigram subwords. Being whitespace-agnostic makes it work uniformly across languages, which is why many multilingual models use it.

**Example:** SentencePiece encodes English and Japanese with the same model, since it never assumes spaces split words.

## Related

- [[bpe]]
- [[tokenizer]]
- [[vocabulary]]

Source: authored
