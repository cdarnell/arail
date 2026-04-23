---
title: "Speculative Decoding: Accelerating LLM Inference"
created: "2026-04-21"
type: research
tags: [inference, speculative-decoding, llm, optimization, draft-model, latency]
status: curating
---

# Speculative Decoding

> Use a fast, cheap model to *guess* several tokens ahead, then let the big model verify them in one parallel pass. Correct guesses are free; wrong ones cost nothing extra. Net effect: 2-6x faster inference with **identical output distribution**.

## Why It Matters

Autoregressive LLM inference is fundamentally sequential — generating K tokens requires K serial forward passes through the model. Each pass is memory-bandwidth bound, leaving GPU compute largely idle. Speculative decoding breaks this bottleneck without retraining, quantizing, or changing the model architecture.

For arail, this is directly relevant to:
- Reducing latency in the AirLLM backend for on-device 70B inference
- Enabling faster agent swarm cycles (ADR-0005 already mentions speculative branching)
- Making real-time chat viable on commodity hardware

---

## Core Concept

```
Traditional:  [tok1] -> [tok2] -> [tok3] -> [tok4] -> [tok5]   (5 serial passes)

Speculative:  Draft model proposes [tok1..tok5] cheaply
              Target model verifies all 5 in ONE parallel pass
              Accept matching prefix, reject + resample from divergence point
              Net: 1-2 passes instead of 5
```

**Key invariant:** The output distribution is *identical* to standard autoregressive sampling. This is lossless acceleration — no quality tradeoff.

### The Rejection Sampling Trick

The mathematical core: if the draft model proposes token `x` with probability `q(x)` and the target assigns `p(x)`:
- Accept with probability `min(1, p(x)/q(x))`
- On rejection, sample from the residual distribution `norm(max(0, p(x) - q(x)))`

This guarantees the final distribution equals `p(x)` exactly, regardless of draft quality. Better drafts just mean higher acceptance rates and more tokens per pass.

---

## Foundational Papers

### 1. Fast Inference from Transformers via Speculative Decoding (2022)
**Leviathan, Kalman, Matias** (Google)
[https://hf.co/papers/2211.17192](https://hf.co/papers/2211.17192) | [arXiv:2211.17192](https://arxiv.org/abs/2211.17192)

The paper that named and formalized speculative decoding. Key insights:
- Hard language-modeling tasks contain easier subtasks approximable by smaller models
- Borrowed the concept of *speculative execution* from CPU architecture
- Demonstrated 2-3x speedup on T5-XXL with identical outputs
- No retraining or architecture changes needed

**This is the "must-read" starting point.**

### 2. Medusa: Simple LLM Inference Acceleration with Multiple Decoding Heads (2024)
**Cai, Li, Geng, Peng, Lee, Chen, Dao** (Princeton/UIUC)
[https://hf.co/papers/2401.10774](https://hf.co/papers/2401.10774)

A different paradigm — instead of a separate draft model, Medusa adds **extra prediction heads** directly to the target model:
- Each head predicts a different future position in parallel
- Tree-based attention mechanism to verify multiple candidate continuations
- Fine-tuned via self-distillation (Medusa-2 variant)
- 60 upvotes on HF — widely adopted in practice
- Simpler deployment (single model) but requires fine-tuning

### 3. EAGLE: Speculative Sampling Requires Rethinking Feature Uncertainty (2024)
**Li, Wei, Zhang, Zhang**
[https://hf.co/papers/2401.15077](https://hf.co/papers/2401.15077)

Operates at the **feature level** rather than token level:
- Predicts second-top-layer features instead of tokens directly
- Addresses the uncertainty gap between feature prediction and token sampling
- Outperforms Medusa, Lookahead, and gpt-fast on MT-bench
- Spawned the EAGLE-2/3 family (see below)

---

## The EAGLE Family & Successors

| Paper | Year | Key Innovation | Speedup |
|-------|------|---------------|---------|
| EAGLE | 2024 | Feature-level drafting | ~3x |
| EAGLE-2 | 2024 | Dynamic draft trees | ~3.5x |
| EAGLE-3 | 2025+ | Improved training + tree pruning | ~4x+ |
| DFlash | 2026 | Block diffusion drafting | **6x+** (2.5x over EAGLE-3) |

### DFlash: Block Diffusion for Flash Speculative Decoding (2026)
**Chen, Liang, Liu**
[https://hf.co/papers/2602.06036](https://hf.co/papers/2602.06036)

Current state-of-the-art. Replaces autoregressive drafting entirely with a lightweight **block diffusion model**:
- Generates all draft tokens in a single forward pass (not sequentially)
- Conditions on context features from the target model
- 6x lossless acceleration, 2.5x faster than EAGLE-3
- 55 upvotes — strong community reception

---

## Self-Speculative Approaches (No Separate Draft Model)

These methods avoid training/maintaining a separate draft model entirely:

### Kangaroo: Lossless Self-Speculative Decoding via Double Early Exiting (2024)
**Liu, Tang, Liu et al.**
[https://hf.co/papers/2404.18911](https://hf.co/papers/2404.18911)

- Uses a shallow sub-network of the target model itself as the draft
- Tiny adapter (67M params vs Medusa's 591M) bridges the capability gap
- Double early-exit: stops drafting when confidence drops below threshold
- 1.68x speedup on Spec-Bench

### CLaSp: In-Context Layer Skip for Self-Speculative Decoding (2025)
**Chen, Shan, Wang et al.**
[https://hf.co/papers/2505.24196](https://hf.co/papers/2505.24196)

- Plug-and-play: skip intermediate layers to create a compressed draft model
- Dynamic programming algorithm optimizes which layers to skip
- No additional training or modules required
- 1.3-1.7x speedup on LLaMA3

### Hydra: Sequentially-Dependent Draft Heads (2024)
**Ankner, Parthasarathy, Nrusimha, Rinard, Ragan-Kelley, Brandon**
[https://hf.co/papers/2402.05109](https://hf.co/papers/2402.05109)

- Extends Medusa by adding sequential dependencies between draft heads
- Improves draft quality without a separate model

---

## Production & Systems Papers

### Batch Speculative Decoding Done Right (2025)
**Zhang, Dey, Mishra et al.** (eBay)
[https://hf.co/papers/2510.22876](https://hf.co/papers/2510.22876)

Critical for production: addresses the **ragged tensor problem** when batching speculative decoding:
- Different sequences accept different numbers of draft tokens
- Breaks position IDs, attention masks, and KV-cache alignment
- Shows several existing implementations violate output equivalence
- EXSPEC: sliding pool + dynamic same-length grouping
- 3x throughput improvement at batch size 8
- Code: https://github.com/eBay/spec_dec

### MagicDec: Breaking the Latency-Throughput Tradeoff (2024)
**Chen, Tiwari, Sadhukhan et al.**
[https://hf.co/papers/2408.11049](https://hf.co/papers/2408.11049)

- Conventional wisdom: speculative decoding only helps at small batch sizes
- MagicDec shows it can help at **high throughput** for moderate-to-long sequences
- Uses sparse KV cache in draft models to address the KV bottleneck
- Intelligent drafting strategy that improves with increasing batch size

### DuoDecoding: Hardware-Aware Heterogeneous Speculative Decoding (2025)
**Lv, Guo, Guo, Qiu**
[https://hf.co/papers/2503.00784](https://hf.co/papers/2503.00784)

- Runs draft model on **CPU**, target model on **GPU** in parallel
- Eliminates draft model GPU overhead entirely
- Reduces time-to-first-token (TTFT) to 83% of conventional speculative decoding
- 2.61x speedup across seven tasks
- Code: https://github.com/KaiLv69/DuoDecoding

---

## Training & Optimization

### LK Losses: Direct Acceptance Rate Optimization (2026)
**Samarin, Krutikov, Shevtsov et al.**
[https://hf.co/papers/2602.23881](https://hf.co/papers/2602.23881)

Standard draft training minimizes KL divergence, but KL is a *proxy* — it doesn't directly maximize acceptance rate:
- LK losses directly target acceptance rate during training
- 8-10% improvement in average acceptance length
- Works across four draft architectures, six target models (8B to 685B)
- Zero computational overhead, drop-in replacement

### TAPS: Task-Aware Proposal Distributions (2026)
**Zbib, Bazzi, Mohanna et al.**
[https://hf.co/papers/2603.27027](https://hf.co/papers/2603.27027)

- Draft model effectiveness depends heavily on training data alignment with downstream tasks
- Specialized drafters + confidence-based routing outperforms generic drafters
- 142 upvotes — highest community engagement in the space

### SpecForge: Open-Source Training Framework (2026)
**Li, Wang, Zhu et al.**
[https://hf.co/papers/2603.18567](https://hf.co/papers/2603.18567)

- Open-source framework for training speculative decoding models
- Target-draft decoupling, hybrid parallelism, optimized kernels
- Production-ready draft models for Qwen3-235B and others

---

## Frontier Directions

### Multimodal Speculative Decoding (2024)
**Gagrani, Goel, Jeon et al.**
[https://hf.co/papers/2404.08856](https://hf.co/papers/2404.08856)

- Language-only models can draft for multimodal models (LLaVA 7B)
- Draft model doesn't need image tokens at all
- 2.37x speedup with a 115M parameter draft model

### OmniDraft: Cross-Vocabulary, Online Adaptive Drafter (2025)
**Ramakrishnan, Yuan, Zhuo et al.**
[https://hf.co/papers/2507.02659](https://hf.co/papers/2507.02659)

- One draft model works with **any** target model (Vicuna, Qwen2, Llama3)
- Online n-gram cache + hybrid distillation for cross-vocabulary mismatch
- Adapts dynamically to user data over time
- Ideal for on-device where you can't maintain multiple drafters

### Diffusion-Based Drafting (2026)
**DFlash** (above) and **DART** ([https://hf.co/papers/2601.19278](https://hf.co/papers/2601.19278))

Moving beyond autoregressive drafting entirely — using diffusion models that generate all draft tokens in parallel.

---

## Benchmarking

### SPEED-Bench (2026)
**Abramovich, Ashkenazi et al.**
[https://hf.co/papers/2604.09557](https://hf.co/papers/2604.09557)

- Standardized benchmark for speculative decoding evaluation
- Diverse semantic domains + realistic serving regimes
- Integrates with vLLM and TensorRT-LLM
- Reveals: synthetic inputs overestimate real-world throughput, optimal draft length depends on batch size

---

## Taxonomy of Approaches

```
Speculative Decoding
|
+-- Separate Draft Model
|   +-- Independent small model (original, SpecForge)
|   +-- Feature-level drafting (EAGLE family)
|   +-- Diffusion-based drafting (DFlash, DART)
|   +-- Cross-vocabulary / universal (OmniDraft)
|
+-- Self-Speculative (no separate model)
|   +-- Extra decoding heads (Medusa, Hydra)
|   +-- Early exit / layer skip (Kangaroo, CLaSp)
|   +-- Recurrent draft head (Recurrent Drafter)
|
+-- Systems / Production
|   +-- Batch correctness (EQSPEC / EXSPEC)
|   +-- Long-context (MagicDec)
|   +-- Heterogeneous hardware (DuoDecoding)
|   +-- Cross-model serving (OmniDraft)
|
+-- Training Improvements
    +-- Direct acceptance optimization (LK Losses)
    +-- Task-aware routing (TAPS)
    +-- Open frameworks (SpecForge)
```

---

## Reading Order (Recommended)

1. **Leviathan et al. 2022** — foundational concepts and math
2. **Medusa 2024** — the "add heads" alternative
3. **EAGLE 2024** — feature-level innovation
4. **Kangaroo 2024** — self-speculative (no extra model)
5. **Batch SD Done Right 2025** — production realities
6. **DFlash 2026** — current SOTA with diffusion drafting
7. **LK Losses 2026** — training optimization
8. **TAPS 2026** — task-aware specialization

---

## Application to arail Systems

### AeroLLM: Layer-Streaming + Speculative Decoding

AeroLLM streams 671B model layers from NVMe (~56 sec/layer load). This makes speculative decoding uniquely valuable:

```
Conventional GPU:    draft overhead competes with target compute
AeroLLM disk-stream: draft model lives in memory, target streams from disk
                     → drafting is essentially FREE relative to layer I/O
```

**Architecture fit:**
- Draft model (68M-600M) permanently resident in 24GB unified memory
- Target model layers stream through MLX, one at a time
- Each verification pass amortizes the expensive layer load across multiple tokens
- DuoDecoding model: draft on CPU/ANE, target on GPU — zero contention
- KV cache budget: draft KV is negligible vs 3.8 GB/prompt target KV at fp16
- With `kv_bits=4`, max batch=14 on 24GB M5 — EXSpec scales efficiently through BS=8

**Estimated impact on throughput:**
- Current: ~0.13 tok/sec aggregate at batch 500, ~22 examples/day
- Layer load is fixed cost, amortized across batch. Speculative decoding multiplies tokens-per-verification-pass
- Conservative 2x on accepted tokens per layer load → doubles effective throughput

### QuKaizen Swarm: Parallel Agent → Batch Serving

Five adversarial agents (Interrogator, Adversary, Evaluator, Corrector, Auto-Research) fire concurrent prompts at the teacher model during SCoTD distillation:

- **This IS batch speculative decoding** — multiple sequences, different lengths, same target model
- Prompt lengths vary by agent role → ragged tensor problem from the Batch SD paper
- **EXSpec length grouping** maps naturally: route agent requests into length-similar batches
- 3x throughput at BS=8 directly compresses the 4-6 week distillation cycle
- **Correctness is critical**: corrupted teacher traces would poison the student's reasoning chain and compound through the 2.5x reweighting feedback loop

### Cross-Vocabulary Drafting (OmniDraft)

If AeroLLM serves different target models (DeepSeek, Llama, Qwen), OmniDraft's "one drafter for all" approach avoids maintaining separate draft models per target family — important for on-device deployment where storage is constrained.

---

## Key Takeaways for Implementation

- **Lossless by design**: output distribution is mathematically identical to standard sampling
- **No retraining of the target model**: all methods leave the big model frozen
- **Draft quality is everything**: acceptance rate determines actual speedup
- **Batch serving is hard**: ragged tensors break naive implementations
- **Hardware heterogeneity is an opportunity**: CPU+GPU parallelism (DuoDecoding) is underexplored
- **Diffusion drafting is the frontier**: DFlash's 6x speedup suggests autoregressive drafting is the bottleneck
- **One drafter for all models**: OmniDraft's cross-vocabulary approach fits on-device deployment

---

*Sources: Hugging Face Papers (hf.co/papers), accessed 2026-04-21. 120+ papers matched "speculative decoding" — this document curates the ~20 most impactful.*
