---
title: "AeroLLM (SLM runtime)"
tags: [world-ai, qukaizen]
aliases: [aerollm-runtime]
---

[ROADMAP] QuKaiZen's OSS inference engine for running SLMs without full GPU residency.

[ROADMAP] AeroLLM is QuKaiZen's open-source inference engine for running small language models on consumer hardware without requiring the model to reside fully in GPU VRAM. AeroLLM the OSS engine exists (separate repo). Its integration into the QuKaiZen bake pipeline — specifically, running the baked domain-specialist SLM at 43+ tok/s as the runtime serving component — is ROADMAP within this pipeline. The label is ROADMAP for the pipeline integration specifically; the engine itself is independently available.

**Example:** Once the ml-engineering SLM is baked, AeroLLM will serve it on the M5 at interactive token rates for training-run triage queries.

## Related

- [[the-bake]]
- [[small-language-model]]
- [[build-time-teacher]]

Source: QuKaiZen CLAUDE.md (AeroLLM — OSS inference engine; 7B@43 tok/s measured); QuKaiZen VISION.md
