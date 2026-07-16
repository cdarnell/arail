---
title: "SCoTD"
tags: [world-ai, fine-tuning]
aliases: [scotd, Symbolic Chain-of-Thought Distillation]
---

Distill a teacher's step-by-step reasoning into a small model via many symbolic CoT traces.

Symbolic Chain-of-Thought Distillation samples multiple chain-of-thought rationales from a large teacher and trains a small student on them, so even a 1-3B model learns to reason in explicit steps rather than pattern-match. It is a key reason small QuKaiZen students can think.

**Example:** A 1.3B student trained on 175B-teacher CoT traces learns to lay out premise, rule, then conclusion on its own.

## Related

- [[distillation]]
- [[raft]]
- [[super-skill]]

Source: knowledge_base/wiki/concepts/SCoTD.md
