---
title: "Draft Model"
tags: [world-ai, performance]
aliases: [draft-model]
---

The small, fast model that proposes candidate tokens in speculative decoding.

The draft model is a smaller, cheaper model that guesses the next several tokens; the large target model then verifies them together. The closer the draft tracks the target, the more tokens are accepted per pass.

**Example:** A 1B draft proposes 5 tokens; the 70B target verifies all 5 in one pass when they agree.

## Related

- [[speculative-decoding]]
- [[verifier]]

Source: QuKaiZen AI Dictionary
