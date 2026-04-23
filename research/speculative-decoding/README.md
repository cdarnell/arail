---
title: "Phase 0: Speculative Decoding ��� Understanding Before Building"
created: "2026-04-21"
type: research
tags: [speculative-decoding, aerollm, qukaizen, phase-0, prototype]
status: active
---

# Phase 0: Speculative Decoding Prototypes

## The Question We're Actually Answering

Before writing any Rust, we need to understand *where* speculative decoding
belongs in our stack. There are three possible answers:

### Answer A: AeroLLM core (always-on, any workload)

Speculative decoding as a default inference mode. Every model served through
AeroLLM gets a draft model paired with it. Interactive users benefit from
lower latency. Distillation benefits from higher throughput.

**The problem:** This requires a compatible draft model for every target model.
A user loads DeepSeek-V3 — where does the draft come from? OmniDraft (one
drafter for all) exists in research but is immature. Cross-vocabulary drafting
is hard. And the generic acceptance rate on arbitrary prompts may only be
40-50%, yielding a modest 1.5-2x speedup.

**When this makes sense:** If AeroLLM evolves into a production serving engine
where latency matters (chat, agent loops, real-time applications).

### Answer B: Distillation-only (QuKaizen teacher acceleration)

Speculative decoding as a throughput multiplier specifically for the teacher
inference pipeline (Phase 1b of Project Nucleus). The teacher model is fixed
for the entire 4-6 week cycle. The domain is fixed. The draft model can be
*trained on the domain traces themselves*.

**The advantage:** Domain-tuned drafters hit 60-70% acceptance rates (vs 40-50%
generic). The TAPS virtuous cycle kicks in — each distillation round improves
the drafter for the next round. And throughput (not latency) is what matters,
so even partial speedups compound across millions of tokens.

**When this makes sense:** Always. This is the immediate, high-confidence win.

### Answer C: Both, but staged

Build speculative decoding into AeroLLM's architecture generically, but
optimize first for the distillation workload where the payoff is measurable
and the constraints are favorable. Interactive serving is Phase 2+.

**This is likely the right answer.** But Phase 0 will tell us for sure.

---

## Why the Batching Strategy Document Changes Everything

The key insight from `02-batching-strategy.md` is that AeroLLM's layer-
streaming architecture is **not a chat engine — it's an offline training-pair
factory**. The 56-second layer load means:

```
Interactive latency:  Terrible (seconds per token)
Batch throughput:     Excellent (tokens amortize across the batch)
```

Speculative decoding interacts with this in a non-obvious way:

### For batch distillation (the current use case):

Each layer load already serves N prompts in the batch. Speculative decoding
means each of those N prompts produces MORE accepted tokens per layer load.
The math compounds:

```
Without speculative decoding:
  1 layer load → N prompts × 1 token each = N tokens

With speculative decoding (acceptance rate α, draft length K):
  1 layer load → N prompts × mean_accepted(α, K) tokens each
  mean_accepted(0.6, 6) ≈ 3.6 tokens
  = 3.6N tokens per layer load
```

**But here's the catch:** The verification of K draft tokens may require
K forward passes through the layer stack, not one. The literature typically
assumes the target model is GPU-resident and can verify all K tokens in a
single batched forward pass. AeroLLM streams layers from disk — can we verify
K tokens in one layer-streaming pass, or do we need K passes?

This is the critical architectural question Phase 0 must answer.

#### Scenario 1: Single-pass verification (best case)

If we can pack all K draft tokens into the same forward pass (as a longer
sequence), then each layer load verifies K tokens simultaneously. The prefetch
worker loads each layer once, we run K tokens through it, done.

This works if the `apply_block` function can process a sequence of K tokens
in one call (prefill-style). The existing StreamingBackend trait suggests this
is possible — `begin_request` takes `&[TokenId]` (a slice), not a single token.

**Speedup: ~K × acceptance_rate multiplier on tokens per layer load.**

#### Scenario 2: Multi-pass verification (worst case)

If each draft token requires a separate layer-streaming pass, we pay K × 56
seconds instead of 1 × 56 seconds. The draft model's speed advantage evaporates
because the bottleneck (disk I/O) scales with K.

**Speedup: None or negative. Speculative decoding would be counterproductive.**

#### Scenario 3: Partial amortization (likely reality)

The first K tokens can be verified in prefill mode (single pass), but the
KV cache state must be correct for each position. On Apple Silicon unified
memory, the layer weights stay resident in the unified memory cache after
the first access, so subsequent tokens in the same pass may hit cache.

**This is what Phase 0b must measure.**

---

## The Three Experiments

### Experiment 0a: Acceptance Rate on Domain Content

**Question:** How well does a generic small model predict a larger model's
outputs on domain-specific content (Linux kernel knowledge)?

**Why it matters:** If acceptance rate is below 40%, speculative decoding
isn't worth the complexity for *any* use case. If it's above 60% on domain
content, the distillation pipeline gets a transformative speedup.

**Setup:**
```
Draft:   Qwen2.5-0.5B (4-bit, ~300MB)
Target:  Qwen2.5-7B (4-bit, ~4GB)
Prompts: 50 domain-specific (Linux kernel) + 50 general-purpose (control)
K:       [4, 6, 8, 12]
Metric:  Mean accepted tokens per draft round, acceptance rate per token
```

**What we learn:**
- Baseline acceptance rate for generic drafter on our domain
- Whether domain content is easier or harder to draft (hypothesis: easier,
  because technical content is more predictable than creative writing)
- Optimal K for our domain (diminishing returns past some point)
- Whether TAPS-style domain tuning is worth pursuing (0c)

**Implementation:** Pure Python with mlx-lm. No AeroLLM dependency. Run both
models in memory (they fit together in ~4.3GB). Implement Leviathan rejection
sampling from scratch — this builds understanding of the core algorithm.

### Experiment 0b: Layer-Streaming Verification Cost

**Question:** Can AeroLLM verify K draft tokens in a single layer-streaming
pass, or does each token require its own pass?

**Why it matters:** This determines whether speculative decoding multiplies
AeroLLM's throughput or divides it. It's the GO/NO-GO gate for the entire
Rust integration.

**Setup:**
```
Model:    Qwen2.5-7B via mlx-lm (simulating layer streaming)
Mode 1:   Standard decode — generate 20 tokens, measure time
Mode 2:   Prefill 20 tokens in one pass, measure time
Mode 3:   Simulate speculative verify — prefill 6 draft tokens, measure time
           per verification round vs. standard 6-step decode
Metric:   Wall-clock time ratio (verification_round / 6_standard_steps)
```

**What we learn:**
- Whether batched token verification is faster than sequential decode
  (it should be on GPU — attention is parallelizable across positions)
- The actual speedup ratio on Apple Silicon MLX
- Whether the memory bandwidth bottleneck (the same one that makes layer
  streaming slow) also limits verification throughput

**Critical nuance:** In standard GPU serving, verification of K tokens is
done as a single forward pass with K input positions — essentially a prefill
of K tokens. This is compute-bound and fast. But AeroLLM's bottleneck is
*memory bandwidth* (loading weights from disk/memory). The question is whether
loading weights once and running K tokens through them is meaningfully faster
than loading weights K times and running one token each time.

On unified memory (Apple Silicon), the answer should be yes — weights loaded
once stay in cache for the K tokens. On disk-streaming (the real AeroLLM path),
weights are loaded once per layer regardless, so K tokens through the same
loaded layer is essentially free.

**This experiment should confirm the "draft is free" thesis.**

### Experiment 0c: TAPS Virtuous Cycle Validation

**Question:** Does fine-tuning the draft model on domain traces improve
acceptance rate enough to justify the TAPS cycle?

**Why it matters:** If domain-tuned drafting gives +10% acceptance length,
then each distillation cycle improves its own infrastructure. The distillation
pipeline becomes self-accelerating. This is the QuKaizen compounding thesis
applied to inference speed.

**Setup:**
```
Phase 1: Measure baseline acceptance rate (from 0a)
Phase 2: LoRA fine-tune Qwen2.5-0.5B on 1000 domain traces
          (use existing Unsloth pipeline in lab/data/plugins/tobi/qmd/finetune/)
Phase 3: Re-measure acceptance rate with tuned draft model
Metric:  Delta in mean accepted tokens per round
```

**What we learn:**
- Whether domain traces are sufficient to improve drafting (vs needing the
  full TICE Corpus, which doesn't exist yet)
- How many traces are needed for meaningful improvement
- Whether the improvement justifies adding draft model tuning to the
  distillation pipeline as a standard step

**Dependency:** Requires domain trace data. If TICE Corpus Phase 1a isn't
far enough along, use synthetic traces from the Qwen2.5-7B target model
answering Linux kernel questions. The traces don't need to be from the
real pipeline — we're measuring acceptance rate improvement, not trace quality.

---

## Decision Matrix After Phase 0

| 0a Result | 0b Result | 0c Result | Decision |
|-----------|-----------|-----------|----------|
| >60% accept | Verify is fast | +10% improvement | Full plan: Rust integration + TAPS cycle |
| >60% accept | Verify is fast | <10% improvement | Rust integration, skip TAPS cycle |
| >60% accept | Verify is slow | Any | Rethink architecture — maybe draft + standard decode, not speculative |
| 40-60% accept | Verify is fast | +10% improvement | Distillation-only with domain-tuned drafter |
| 40-60% accept | Verify is fast | <10% improvement | Marginal — maybe self-speculative (CLaSp) instead |
| <40% accept | Any | Any | Speculative decoding not viable. Pivot to other optimizations |

---

## What These Experiments Teach Us (Beyond Numbers)

### Building intuition for rejection sampling

Experiment 0a requires implementing the Leviathan algorithm by hand. This
builds deep understanding of:
- Why the output distribution is provably identical to standard sampling
- How acceptance rate relates to KL divergence between draft and target
- Why temperature matters (higher temp → more randomness → lower acceptance)
- Why greedy decoding has the highest acceptance rate (no randomness to disagree on)

### Understanding AeroLLM's cost model

Experiment 0b forces us to articulate the difference between:
- **Compute-bound verification** (GPU has weights, runs K tokens: fast)
- **Memory-bound verification** (weights must be loaded, K tokens share the load: medium)
- **I/O-bound verification** (weights stream from disk, K tokens share the stream: the real question)

### Connecting research to production

Experiment 0c bridges the gap between "papers report 3-4x speedup" and
"what speedup do we get on our domain, our models, our hardware." Every
speculative decoding paper benchmarks on MT-Bench or HumanEval — neither
of which resembles Linux kernel reasoning traces.

---

## File Structure

```
research/speculative-decoding/
├── README.md                          ← this file
├── 0a-acceptance-rate.py              ← Experiment 0a
├── 0b-verification-cost.py            ← Experiment 0b
├── 0c-taps-validation.py             ← Experiment 0c
└── results/
    ├── 0a-acceptance-rate.json        ← raw measurements
    ├── 0b-verification-cost.json
    └── 0c-taps-validation.json
```

Results feed back into `research/aerollm/04-measurement-log.md` as new rows.

---

## Prerequisites

```bash
pip install "arail[mlx]"   # or: pip install mlx mlx-lm
# Models will be downloaded on first run from HuggingFace
# Qwen2.5-0.5B-4bit: ~300MB
# Qwen2.5-7B-4bit:   ~4GB
# Total memory needed: ~8GB (both models + KV cache + activations)
```
