---
title: "Nucleus (bake engine)"
tags: [world-ai, qukaizen]
aliases: [nucleus-bake-engine]
---

[ROADMAP] QuKaiZen's training pipeline for baking domain-specialist SLMs.

[ROADMAP] Nucleus is the QuKaiZen training infrastructure that takes a baked corpus (compiled World + corpus_sha256 manifest) and runs the fine-tuning/distillation pipeline to produce a sealed domain-specialist SLM. The training run lives on the M5 (Apple Silicon); engine-side plumbing (corpus preparation, bake-corpus.mts) exists today, but the full end-to-end Nucleus bake pipeline is in development. ROADMAP because no sealed specialist SLM has been produced yet.

**Example:** Nucleus will take the ml-engineering bake corpus (corpus_sha256-pinned) and produce a 7B domain-specialist SLM in the RAW→COMPILED→BAKED lifecycle.

## Related

- [[the-bake]]
- [[corpus-sha256]]
- [[baked-stage]]
- [[domain-specialist-model]]
- [[small-language-model]]

Source: QuKaiZen CLAUDE.md (Nucleus: company hub, bake pipeline); QuKaiZen THEME.md; QuKaiZen VISION.md
