---
title: "RAFT"
tags: [world-ai, fine-tuning]
aliases: [raft, Retrieval Augmented Fine-Tuning]
---

Fine-tuning that teaches a model to reason over retrieved docs while ignoring distractors.

RAFT trains on a question plus a mix of oracle (relevant) and distractor (irrelevant) documents, teaching the model to cite the right source and ignore noise. The result reasons through imperfect retrieval rather than memorizing — domain-specific RAG baked into the weights.

**Example:** For a kernel-bug question, RAFT shows the real commit (oracle) plus two unrelated patches (distractors); the model learns to ground its answer in the oracle.

## Related

- [[fine-tune]]
- [[distillation]]
- [[scotd]]
- [[super-skill]]

Source: knowledge_base/wiki/concepts/RAFT.md
