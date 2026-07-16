---
title: "Constrained Decoding"
tags: [world-ai, inference]
aliases: [constrained-decoding, guided decoding, grammar-constrained decoding]
---

Restrict generation at each step to tokens allowed by a grammar or schema, guaranteeing valid output.

Constrained (guided) decoding masks the logits so only tokens permitted by a formal grammar, regex, or JSON schema can be sampled, guaranteeing the output parses. It is how reliable structured output and JSON modes are enforced without hoping the model complies.

**Example:** A JSON schema constraint makes every generated character legal, so the result always parses.

## Related

- [[structured-output]]
- [[function-calling]]
- [[sampling]]
- [[logits]]

Source: authored
