---
title: "HalluLens"
tags: [world-ai, training]
aliases: [hallulens, LLM hallucination benchmark]
---

A benchmark for measuring how often an LLM hallucinates — asserts unsupported or fabricated facts.

HalluLens is a hallucination benchmark that separates extrinsic hallucination (claims grounded in no source) from intrinsic hallucination (contradicting the given input), and probes models with tasks designed to surface confident-but-false answers. It exists because fluency hides unreliability — a model can sound right while being wrong.

**Example:** Asked to summarize a paper that does not exist, a hallucinating model invents authors and results; HalluLens scores whether it fabricates or correctly declines.

## Related

- [[eval]]
- [[benchmark]]

Source: authored
