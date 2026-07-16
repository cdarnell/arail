---
title: "IFEval"
tags: [world-ai, training]
aliases: [ifeval, Instruction-Following Eval]
---

A benchmark of machine-verifiable instructions that measures how precisely a model obeys format and constraint requests.

IFEval (Instruction-Following Eval) uses prompts whose compliance can be checked programmatically — answer in exactly three bullet points, avoid a given word, respond in JSON. Because each rule is machine-verifiable, it scores obedience objectively, with no human or judge model in the loop.

**Example:** Given an instruction to write two paragraphs and end with a specific word, IFEval checks both conditions automatically; missing either one counts as a fail.

## Related

- [[benchmark]]
- [[eval]]
- [[mmlu]]

Source: authored
