# Disk-Streamed Inference for 1 TB-Class Models

**Scope:** Can we serve a 1 TB model from NVMe using layer streaming and MoE expert offload (the approach AeroLLM implements)? How fast is "fast enough," and what should the oglab overlays measure?

**Date:** 2026-04-17

---

## 1. What does a "1 TB model" actually mean?

The 1 TB figure bounds the weights, not the activation or KV-cache footprint. Three realistic anchors:

| Model (approx)             | Params | Precision | On-disk size |
|----------------------------|--------|-----------|--------------|
| Llama 3.1 405B             | 405 B  | FP32      | ~1.6 TB      |
| Llama 3.1 405B             | 405 B  | FP16      | ~810 GB      |
| DeepSeek-V3/R1 (MoE 671B)  | 671 B  | FP8       | ~671 GB      |
| Hypothetical 500 B dense   | 500 B  | FP16      | ~1.0 TB      |
| Hypothetical 2 T MoE       | 2 T    | INT4      | ~1.0 TB      |

Two different shapes fit under "1 TB": a *dense* model where every token touches every parameter, and a *sparse MoE* where every token touches only a small fraction. The right optimization is very different for each, which is why this question has two answers.

---

## 2. The storage bandwidth ceiling

Decode throughput for a disk-streamed dense model is bounded by:

```
tokens/sec  <=  NVMe_read_bandwidth  /  bytes_read_per_token
```

| NVMe tier              | Practical sustained read | Notes                               |
|------------------------|--------------------------|-------------------------------------|
| SATA SSD               | ~0.5 GB/s                | Do not attempt this                 |
| PCIe 3.0 NVMe          | 2–3 GB/s                 | Older consumer drives               |
| PCIe 4.0 NVMe          | 5–7 GB/s                 | e.g. Samsung 980 PRO                |
| PCIe 5.0 NVMe          | 10–14 GB/s               | e.g. Crucial T705, SK hynix P51     |
| Apple unified NVMe     | ~17.5 GB/s               | M4 Pro/Max, measured by Flash-MoE   |
| RAID-0 x4 PCIe 5.0     | 30–50 GB/s (claimed)     | Saturates PCIe lanes; cache-hostile |

For a **1 TB dense model** reading every byte per token, the best-case ceiling is `1 TB / 17.5 GB/s ≈ 57 seconds per token`. That is the fundamental reason dense 1 TB inference from disk is not viable interactively without a sparsity trick.

**MoE is the sparsity trick.** With DeepSeek-V3–style routing (37 B of 671 B active per token), per-token disk traffic drops to roughly `37 GB × (1 − cache_hit_rate)`. At the OS page cache's naturally-observed ~71% hit rate, that's closer to 10–11 GB read per token — now a 0.6–2 tok/s regime is in reach on a single PCIe 4 drive, and 2–5 tok/s on PCIe 5 / Apple silicon.

---

## 3. Layer-wise streaming for dense models (AeroLLM, and prior art)

The canonical approach — implemented by AeroLLM and historically demonstrated by AirLLM — is structural, not clever. Shard the checkpoint into per-layer files (80–100 shards for a 70B model) and run a strict sequence per token:

```
for layer in 0..N:
    load layer N from NVMe -> GPU
    compute activations
    free layer N
    prefetch layer N+1        # AeroLLM runs this multi-threaded; AirLLM historically overlapped ~10%
```

**Observed performance:**

- 70B on a 4 GB VRAM + NVMe laptop: **0.7–4.3 tok/s**, with 4.3 tok/s on an RTX 3050 + good NVMe being the high end
- 70B on SATA SSD: often sub-1 tok/s — NVMe provides 3–5× speedup
- 405B on 8 GB VRAM: demonstrated to run, but sub-1 tok/s is realistic
- Peak VRAM reduction: ~95% vs full load

**Why it's slow for dense at 1 TB:** every token re-reads every layer. Prefetching one layer ahead hides ~10% of I/O, not 90%. You are stuck at the bandwidth ceiling above.

**Where layer streaming shines:** batch or offline workloads where latency is irrelevant, and as a teaching artifact — the architecture is easy to reason about and instrument. AeroLLM's multi-threaded prefetch push pushes the latency ceiling down but doesn't change the structural story.

---

## 4. MoE expert offload: the actually-fast path

For a sparse model the math is radically different. Only non-expert weights (attention, embeddings, routers) plus the *activated* experts need to be resident. The rest can live on disk.

**Typical tiered layout** (used by KTransformers, Flash-MoE, HybriMoE):

| Tier     | Medium           | Contents                                        |
|----------|------------------|-------------------------------------------------|
| Hot      | GPU VRAM         | Non-expert weights, activations, expert cache   |
| Warm     | CPU DRAM         | Recently-used experts (LRU or learned cache)    |
| Cold     | NVMe SSD         | The long tail of rarely-routed experts          |

**Measured throughput:**

| System / Hardware                          | Throughput                 |
|--------------------------------------------|----------------------------|
| DeepSeek-V3 671B, 8×MI300X expert parallel | 21,224 tok/s (server-scale) |
| DeepSeek-V3 671B on A100 + 2×Xeon, hybrid  | 70 tok/s prefill, 4.68 tok/s decode |
| KTransformers on MoE                       | 4.62–19.74× prefill, 1.25–4.09× decode vs baseline |
| Flash-MoE (Qwen3 397 B) on 48 GB M-series  | 4.36 tok/s                 |
| Unsloth DeepSeek-R1 1.58-bit on RTX 4090   | <5 tok/s                   |

The interesting line is Flash-MoE: a 397 B model on a *laptop-class* unified-memory machine at 4.36 tok/s. The OS page cache on hot routes hit ~71% naturally — no custom cache manager needed.

---

## 5. Latency hiding: where the 2026 research is moving

The single biggest lever is **prefetching experts before the router picks them**. Three techniques worth teaching:

1. **MoE-SpeQ (2511.14102).** A small draft model predicts the next few tokens, which means their experts are predictable. The main model prefetches those experts from disk *while* the draft is still running, overlapping I/O with compute. Effectively removes SSD latency from the critical path when prediction is accurate.

2. **PreScope / LLaPor.** A learned "Layer-Aware Predictor" beats heuristic last-layer-same-expert prefetching. Trained per model.

3. **HybriMoE.** Dynamic intra-layer scheduling + impact-driven prefetching + score-based caching. Closes the CPU-GPU utilization gap to near 100% where KTransformers sits around 75%.

4. **Expert Deferral (KTransformers).** Reorders which experts run on CPU vs GPU to maximize overlap. Cheap and generic.

All four are compatible with NVMe as the cold tier — they change *which* experts get fetched eagerly, not whether fetching is needed.

---

## 6. Back-of-envelope response time for oglab's target

Assume oglab wants to demo "interactive-feeling" inference on a 1 TB model on a single workstation. Three scenarios:

**Scenario A — Dense 500 B FP16 via AeroLLM, PCIe 4 NVMe (7 GB/s)**

- Per-token read: ~1 TB (every layer, every token)
- Ceiling: ~7 seconds per token
- TTFT for a 50-token prompt: ~6 minutes
- Verdict: teaching demo only

**Scenario B — DeepSeek-V3-class MoE (671 B FP8) with KTransformers + PCIe 5 NVMe**

- Per-token read (with ~71% page-cache hit): ~5–10 GB
- Ceiling: 1.5–3 tok/s on one drive
- With speculative prefetch (MoE-SpeQ-style): realistic 3–6 tok/s
- TTFT for 50-token prompt: 8–20 s
- Verdict: usable for non-chat workloads (code generation, agentic steps)

**Scenario C — Same MoE + RAID-0 × 2 PCIe 5 NVMe + draft-model prefetch**

- Effective read bandwidth: ~25 GB/s
- Active weight read drops near cache ceiling of ~1–2 GB/token with high hit rate
- Realistic: 10–15 tok/s decode
- Verdict: genuinely interactive

The shape of the curve is: moving from SATA → PCIe 4 → PCIe 5 → RAID 0 each give roughly 2× linear speedups, but **switching from dense streaming to MoE + predictive prefetch is a 10–50× jump**. Do that one first.

---

## 7. Energy caveat worth flagging in the overlays

A recent study ("SSD Offloading for LLM MoE Weights Considered Harmful in Energy Efficiency," 2508.06978) measured that **SSD read energy can be ~80% of per-token energy** for disk-streamed MoE. Interactive latency is achievable but the joules-per-token story is ugly compared to DRAM-resident inference. For an academic lab this is a feature, not a bug — it makes a great overlay metric and a clean argument for when DRAM is worth the budget.

---

## 8. Recommendations for oglab

Tie the feature work to the teaching mission — every optimization should surface as a live overlay.

**Instrumentation to add (ranked by teaching value):**

1. **Per-token timeline overlay.** Show phases as a stacked bar: router → expert fetch (disk) → expert fetch (DRAM) → GEMM → sampling. This single visualization teaches 80% of the story.
2. **Storage bandwidth gauge.** Current MB/s read from NVMe vs ceiling. A flat line at the ceiling is the "we are I/O-bound" signal.
3. **Page-cache hit-rate counter.** Literal `/proc/...` numbers; shows the 71% figure emerging in real time.
4. **Expert hotness heatmap.** Which experts got fetched from cold tier this minute. Makes the sparsity concrete.
5. **Draft-model accuracy vs prefetch hit-rate** (only if MoE-SpeQ-style prefetching is enabled). Shows the speculative-decoding tradeoff.
6. **Joules-per-token** (if platform exposes RAPL / IPMI). Ties to the energy caveat above.

**Simplification / consolidation angles** (since you flagged over-engineering):

- **Pick one sparse model family** for the "big model" showcase (DeepSeek-V3 / Qwen3-MoE / Mixtral descendants). Maintaining both a 405 B dense streaming path AND a 671 B MoE path is expensive; the MoE path teaches more and runs faster.
- **Prefer KTransformers over a hand-rolled streamer.** It already does expert-cache, CPU-GPU scheduling, and 3-tier (GPU/CPU/disk) prefix cache reuse. Your value-add is the overlay layer, not a competing runtime.
- **Use AeroLLM for the dense path** — don't try to make it fast per-prompt. The contrast with MoE is pedagogical gold; concurrent-prompt batching is where AeroLLM wins back throughput.
- **Make the storage tier a pluggable config,** not a code path. SATA / PCIe 4 / PCIe 5 / tmpfs should be a single config knob so students can observe the bandwidth ceiling move.

---

## Sources

- [AeroLLM (OGLab's Rust runtime — MLX + CUDA)](https://github.com/cdarnell/aerollm)
- [AirLLM (historical prior art for layer streaming)](https://github.com/lyogavin/airllm)
- [AirLLM: Run 70B Models on 4GB GPUs — hype vs reality](https://nerdleveltech.com/airllm-run-70b-llm-single-4gb-gpu)
- [Expert Offloading to CPU or NVMe (apxml)](https://apxml.com/courses/mixture-of-experts-advanced-implementation/chapter-4-efficient-moe-inference/expert-offloading)
- [Flash-MoE: 397 B on a 48 GB MacBook](https://lilting.ch/en/articles/flash-moe-qwen35-397b-metal-inference)
- [Flash-MoE benchmarks & quality tradeoffs (2026)](https://www.buildmvpfast.com/blog/flash-moe-weight-streaming-benchmarks-quality-tradeoffs-2026)
- [KTransformers paper (SOSP '25)](https://madsys.cs.tsinghua.edu.cn/publication/ktransformers-unleashing-the-full-potential-of-cpu/gpu-hybrid-inference-for-moe-models/SOSP25-chen.pdf)
- [HybriMoE: hybrid CPU-GPU scheduling for MoE](https://arxiv.org/abs/2504.05897)
- [MoE-SpeQ: speculative prefetch for MoE offload](https://arxiv.org/abs/2511.14102)
- [PreScope: prefetch for resource-constrained MoE](https://arxiv.org/html/2509.23638)
- [I/O characterization of LLM + KV offload to NVMe](https://atlarge-research.com/pdfs/2025-cheops-llm.pdf)
- [INF2: near-storage processing for LLM inference](https://arxiv.org/html/2502.09921v1)
- [SSD offloading considered harmful for energy](https://arxiv.org/html/2508.06978v1)
- [DeepSeek-V3 / R1 hybrid inference measurements](https://groundy.com/articles/running-deepseek-r1-locally-hardware-requirements-quantization-and-real-throughput/)
- [21K tok/s DeepSeek on 8×MI300X (Moreh)](https://moreh.io/technical-report/21k-output-tokens-per-second-deepseek-inference-on-amd-instinct-mi300x-gpus-with-expert-parallelism-251113/)
- [Unsloth DeepSeek-R1 1.58-bit dynamic quant](https://unsloth.ai/blog/deepseekr1-dynamic)
- [Llama 3.1 405B self-hosting (Tribe AI)](https://www.tribe.ai/applied-ai/self-hosting-llama-3-1-405b-fp8-bringing-superintelligence-in-house)
