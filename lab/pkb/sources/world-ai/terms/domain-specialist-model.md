---
title: "Domain-specialist model"
tags: [world-ai, fine-tuning]
aliases: [domain-specialist-model]
---

A model adapted to excel in one domain by fine-tuning, distillation, and domain-adaptive pretraining.

A domain-specialist model is a foundation model adapted via continued pretraining, fine-tuning, and/or distillation to specialize in a particular domain (medical, legal, ML engineering, horticulture). By trading general capability for domain depth, a specialist can outperform a much larger generalist on domain tasks. The core mechanism: a smaller model with deep domain grounding can match or exceed a larger generalist on in-domain benchmarks.

**Example:** An ML-engineering specialist trained on practitioner-sourced domain material can triage training-run failures more reliably than a general-purpose model that lacks domain grounding.

## Related

- [[small-language-model]]
- [[knowledge-distillation]]
- [[continued-pretraining]]

Source: Gururangan et al. — Don't Stop Pretraining arXiv:2004.10964; HF domain adaptation docs; OLMo (EleutherAI) domain specialist experiments
