---
title: "Encoder-Decoder"
tags: [world-ai, architecture]
aliases: [encoder-decoder, seq2seq]
---

A two-stack design: an encoder reads the full input, a decoder generates output attending to it via cross-attention.

The original transformer is encoder-decoder: a bidirectional encoder builds a representation of the whole input, and an autoregressive decoder generates the output, using cross-attention to look back at the encoding. It suits transduction tasks like translation and summarization, where input and output are distinct sequences.

**Example:** Translation: the encoder ingests the French sentence; the decoder emits English, cross-attending to the encoded French at each step.

## Related

- [[decoder-only]]
- [[cross-attention]]
- [[transformer]]
- [[attention]]

Source: authored
