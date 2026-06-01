---
title: "ADR-0001: AI-Engineer Domain Specialization of the Default Model"
description: "How ARAIL's default model becomes a real AI-engineering domain expert — corpus + research distillation onto a permissive small base (Llama 3.2), not just a persona prompt."
category: Architecture
order: 1
tags:
  - adr
  - model
  - distillation
  - nucleus
  - licensing
audience: architect
related:
  - BLUEPRINTS
  - design
  - CERTIFIED_MODELS
---

# ADR-0001: AI-Engineer Domain Specialization of the Default Model

**Status:** Accepted (target architecture) — interim persona-wrap shipping now; specialized artifact is the planned upgrade.
**Date:** 2026-05-31
**Deciders:** QuKaiZen
**Supersedes / relates:** the two-tier model strategy (`sprints/2026-05-30-model-hosting-reframe/MODEL-TIERS-V2.md`), the dormant self-hosted build/host lane (`scripts/build_ai_eng.{sh,py}`, `ARAIL_AI_ENG_SELFHOSTED=1`).

## Context

ARAIL ships an "AI engineer" as its default assistant. Today that assistant
is a **persona-wrap**: a permissive base model (`llama-ai-eng` = Llama-3.2-1B-Instruct)
wrapped with an AI-engineer SYSTEM prompt via an Ollama Modelfile. This is
honest, shippable today, and runs on a 16 GB machine — but it is *not* a model
whose weights actually encode AI-engineering expertise. The "expert" behavior
comes from the prompt, not from training.

We want the default model to be a genuine **domain-specialized AI engineer** —
weights that have been taught AI/ML engineering knowledge, reasoning patterns,
and idioms — while staying small enough for the everyday tier and permissively
licensed enough for an MIT blueprint that people fork and redistribute.

We have **already proven this approach once**: a prior specialization run
produced an AI-engineer adapter on a Qwen base via QuKaiZen's Nucleus pipeline
(the Super Skill Distillation Pipeline / SSDP). This ADR records the approach as
the target architecture so it is repeatable on a "decent" base like Llama 3.2,
and so the moving parts (corpus, base choice, licensing, packaging) are
deliberate rather than rediscovered each time.

## Decision

Produce the default AI-engineer model by **specializing a permissive small base
through an AI-engineering corpus + research distillation pipeline (Nucleus/SSDP)**,
then package the result through ARAIL's existing build-and-host lane.

The pipeline, end to end:

1. **Base selection** — a permissive, small, instruction-tuned base. Current
   choice: **Llama-3.2-1B-Instruct** (everyday tier, ~0.9 GB Q4, 16 GB-safe;
   Llama 3.2 Community License). A larger permissive base (e.g. Llama-3.2-3B)
   is the capability lever if 1B underperforms on code/reasoning. The base
   **must** be one ARAIL can redistribute (see Licensing).
2. **Corpus + research** — run the base through the curated AI-engineering
   corpus and the research/distillation loop (Nucleus/SSDP) to produce a
   **LoRA adapter** that encodes the AI-engineer domain. The adapter is the
   portable specialization artifact.
3. **Merge + convert + quantize** — merge the adapter into the base, convert to
   GGUF, and quantize (Q4_K_M) via `scripts/build_ai_eng.{sh,py}` (OOM-guarded,
   bench-gated, idempotent).
4. **Self-host + distribute** — publish the quantized GGUF to the self-hosted
   ladder (HuggingFace primary, GitHub Release mirror, optional CDN), pin its
   sha256 in `pyproject.toml`, and activate the lane behind
   `ARAIL_AI_ENG_SELFHOSTED=1`. Setup then pulls the *real* specialized model
   instead of wrapping the base.

Until step 2 has produced a Llama-matched adapter, the **persona-wrap remains
the shipping default** — it is the honest interim, not the destination.

## Licensing (load-bearing)

- The base **must remain permissively redistributable**. Llama 3.2 Community
  License is acceptable for free, non-commercial blueprint sharing **but
  imposes obligations**: display "Built with Llama" and begin any distributed
  model name with "Llama" (hence `llama-ai-eng`). Apache-2.0 bases (e.g.
  Qwen2.5-7B, used for the maximus deep persona) carry no naming clause.
- **Research/non-commercial-licensed bases are disqualified** for the default
  (this is why Qwen2.5-3B was rejected earlier — its Qwen Research License
  conflicts with ARAIL's MIT fork/redistribute thesis).
- The specialized GGUF is a **derivative work**: the base license + attribution
  (`NOTICE`, bundled `licenses/`) travel with every redistributed artifact —
  HF model card, GitHub Release, CDN.

## Consequences

**Positive**
- The default assistant becomes a real domain expert, not a prompt veneer —
  the core differentiator of an "AI lab" blueprint.
- The approach is repeatable across bases (proven on Qwen, now targeting Llama)
  and across domains (the same pipeline can specialize other personas).
- The packaging/hosting machinery already exists (dormant), so step 3–4 are
  wiring, not new design.

**Negative / risks**
- **Adapter–base architecture must match.** A LoRA trained on one base does not
  apply to another (we hit this: a Phi-3.5-mini adapter could not fuse onto
  Qwen/Llama). The corpus run must target the *exact* deployed base.
- Specialization is a real training cost (corpus curation + compute), separate
  from ARAIL's runtime; it happens in Nucleus, not on the user's machine.
- Quality at 1B is bounded — a small base limits how much expertise the weights
  can hold; 3B is the upgrade lever, traded against the 16 GB floor.
- More distribution surface to keep license-compliant and digest-pinned.

## Alternatives considered

- **Persona-wrap as the final answer** — rejected as the *destination* (no real
  domain weights), kept as the *interim* (honest, ships today).
- **Larger base (7B+) as the everyday default** — rejected for the 16 GB floor;
  the 7B lives in the maximus *deep* tier instead.
- **Research-licensed bases (Qwen-3B)** — rejected on licensing.
- **Cloud frontier model as default** — rejected; violates ARAIL's local-first,
  airgapped-by-default principle (cloud stays an opt-in Compute Source).

## References

- `sprints/2026-05-30-model-hosting-reframe/MODEL-TIERS-V2.md` — current two-tier model design.
- `scripts/build_ai_eng.{sh,py}` — merge → convert → quantize → publish lane.
- `NOTICE`, `licenses/` — base-model attribution that travels with the artifact.
- KB primer `09-choosing-a-base-model` (model-building seed pack) — the user-facing version of the base-selection logic above.
