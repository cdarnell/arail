---
title: "Stop Sequence"
tags: [world-ai, inference]
aliases: [stop-sequence, stop token]
---

A string that, once generated, halts decoding — used to bound output and separate turns.

A stop sequence is one or more strings that terminate generation when produced, so the model doesn't run on past the intended boundary. They mark turn ends, close structured fields, or cap output. Distinct from the model's learned end-of-sequence token, stop sequences are caller-specified at request time.

**Example:** Setting a stop sequence of '\nUser:' keeps the model from hallucinating the user's next turn.

## Related

- [[system-prompt]]
- [[sampling]]
- [[tokenizer]]
- [[determinism]]

Source: authored
