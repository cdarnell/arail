---
title: "Eval"
tags: [world-ai, training]
aliases: [eval, evaluation, evals]
---

The practice of measuring model quality with repeatable tests — from public benchmarks to task-specific graders.

An eval is any repeatable measurement of how well a model does something: a public benchmark, a private held-out set, an LLM-as-judge rubric, or a unit-test-style check. Good evals are the steering wheel of model building — without them you cannot tell whether a change helped. QuKaiZen's certification gates are the evals a student model must pass before it graduates.

**Example:** Before shipping a fine-tune you run an eval suite — MMLU for knowledge, GSM8K for math, IFEval for instruction-following — and only ship if every score holds or improves.

## Related

- [[benchmark]]
- [[mmlu]]
- [[gsm8k]]
- [[ifeval]]
- [[kice]]

Source: authored
