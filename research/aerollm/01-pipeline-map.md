# 01 — Inference Pipeline Map

**Purpose.** Give the life of a single decoded token a common vocabulary across CUDA (AeroLLM) and MLX (AeroLLM) paths, so when someone says "the bottleneck is the prefetch stage" everyone means the same thing.

**How to use.** When you run a bench, populate the "Last measured (ms)" columns at the bottom. Over time the columns will tell us which stages are worth attacking.

---

## The 8 stages of a token

Per-token, the loop hits these stages in order. Inside each we list the protocol / tech / method, the relevant knobs from `config/tuning.yml` (CUDA) and `config/tuning-mlx.yml` (MLX), and whether the stage amortizes across a batched prompt set.

### Stage 0 — Scheduler / request admission

Decide *what* to run this pass. Trivial for single-prompt; the whole game for batched / continuous-batching. The runtime's main research lane lives here (see `02-batching-strategy.md`).

| Aspect            | CUDA (AeroLLM)                                          | MLX (AeroLLM)                                                              |
|-------------------|--------------------------------------------------------|----------------------------------------------------------------------------|
| What happens      | Pick next prompt(s), merge into active set             | Same — plus optional prompt-cache reuse                                    |
| Tech / method     | Python loop; no native batcher in upstream AeroLLM      | `mlx_lm.generate` wraps a single-prompt path; we'd add a batcher on top    |
| Knobs             | *(scheduler-level `batch_size` + admission policy)*    | `prompt_cache_enabled`, new `batch_size` knob to add                       |
| Batch-amortizable | N/A — this stage *creates* the batch                   | Same                                                                       |

### Stage 1 — Layer weight load (disk → host memory)

The dominant cost. For a 70B model at 4-bit, each layer is ~1–2 GB; N=80 layers means 80–160 GB read per token at 1 prompt. Batching divides this by batch size.

| Aspect            | CUDA (AeroLLM)                                                        | MLX (AeroLLM)                                                   |
|-------------------|----------------------------------------------------------------------|-----------------------------------------------------------------|
| What happens      | `torch.load` / `safetensors.safe_open` on layer N shard              | `mx.load(shard, stream=true)` via mmap; zero-copy-ish on Apple  |
| Tech / method     | Sharded safetensors, blocking reads, one layer at a time             | mmap + lazy materialization; layer-level still to be built       |
| Knobs             | AeroLLM's `compression` (bitsandbytes 4/8bit), `prefetching` (on/off) | (MLX streaming layer not shipped yet — see `mlx-streaming-plan.md`) |
| Batch-amortizable | **YES** — one load serves all N batched prompts on this layer       | **YES** — same                                                  |
| Dominant factor   | NVMe read bandwidth: ceiling of ~`sum(layer_bytes) / read_GB_s`      | Unified NVMe: ~17.5 GB/s on M4 Pro/Max                          |

### Stage 2 — Host-to-device transfer (CUDA only)

Not a separate stage on Apple — unified memory means Stage 1 already addressable.

| Aspect            | CUDA (AeroLLM)                                                | MLX (AeroLLM)                 |
|-------------------|--------------------------------------------------------------|-------------------------------|
| What happens      | `cudaMemcpyAsync` host → device with pinned memory           | *(no-op; unified)*            |
| Tech / method     | Pinned host buffers, async CUDA stream, PCIe 4/5             | *(none)*                      |
| Knobs             | pinned-memory enable, CUDA stream count                      | *(none)*                      |
| Batch-amortizable | **YES**                                                      | *(n/a)*                       |
| Dominant factor   | PCIe 4 = ~25 GB/s practical, PCIe 5 = ~50 GB/s               | *(n/a)*                       |

### Stage 3 — Layer prefetch overlap

While Stage 4 computes on layer N, Stages 1–2 for layer N+k run in the background. The whole point of prefetching is to hide Stage 1/2 behind Stage 4.

| Aspect            | CUDA (AeroLLM)                                                                     | MLX (AeroLLM)                                                          |
|-------------------|-----------------------------------------------------------------------------------|------------------------------------------------------------------------|
| What happens      | Async worker pulls layer N+1 from disk while compute runs on N                    | Thread + queue loader (mlx-lm is sync); `stream_prefetch_k` ahead      |
| Tech / method     | `asyncio.to_thread` or a dedicated loader thread; ~10% overlap upstream           | Custom `prefetch.py` (planned) — `k`-step lookahead                    |
| Knobs             | `stream_prefetch_k` lookahead, `max_in_flight_loads`                              | `stream_prefetch_k` (0–4), `stream_resident_blocks` (1–8)              |
| Batch-amortizable | Cost amortized; benefit compounds with batch size                                 | Same                                                                   |
| Notes             | Upstream AeroLLM prefetches 1 ahead and gets ~10% of load time hidden              | Untried on MLX — prefetch gain depends on disk vs compute ratio        |

### Stage 4 — Compute (GEMM + attention + norm + router)

The only stage where batching directly reduces *per-prompt* compute — a batched matmul is cheaper than N single matmuls. Also the stage where KV cache is read/written.

| Aspect            | CUDA (AeroLLM)                                                               | MLX (AeroLLM)                                                                |
|-------------------|-----------------------------------------------------------------------------|------------------------------------------------------------------------------|
| What happens      | Per-layer forward: attn → FFN (or routed experts for MoE) → norm            | Same, on Metal via MLX kernels                                               |
| Tech / method     | PyTorch + cuBLAS; optional FlashAttention-2                                 | MLX primitives; MPS kernels; no FlashAttention yet on MLX                    |
| Knobs             | `bitsandbytes_precision`, KV cache dtype, attention impl, seq length        | `kv_bits`, `quantized_kv_start`, `max_kv_size`, `prefill_step_size`          |
| Batch-amortizable | Partial — GEMM scales sublinearly in batch; attention scales roughly linearly | Same                                                                      |
| Dominant factor   | For small batch → I/O bound; for large batch → compute bound (good problem) | Same, with MLX's compute/memory ratio different from CUDA                    |

### Stage 5 — KV cache read / append

On the first token of a prompt (prefill), K and V are built for every token in the prompt. On subsequent decode steps, only the new token's KV is appended and prior KV is read.

| Aspect            | CUDA (AeroLLM)                                                         | MLX (AeroLLM)                                                           |
|-------------------|-----------------------------------------------------------------------|-------------------------------------------------------------------------|
| What happens      | Append new K,V for current token; read all prior K,V during attention  | Same; MLX supports online KV quantization                               |
| Tech / method     | Per-layer KV tensors, resident on GPU; grows monotonically with context | Unified memory KV tensors; supports `kv_bits` online                    |
| Knobs             | max context, KV dtype (fp16/int8/int4), sliding window, paged KV      | `kv_bits` (fp16/8/4), `quantized_kv_start`, `max_kv_size`              |
| Batch-amortizable | NO — KV is per-prompt; memory scales linearly with batch size         | NO — same limitation, and this is the main batch-size ceiling           |
| Notes             | This is the primary memory pressure for large batches                 | KV quant is THE biggest MLX throughput knob for long-context work       |

### Stage 6 — Layer unload / eviction

Free VRAM (or unified memory slot) to make room for layer N+1.

| Aspect            | CUDA (AeroLLM)                                                         | MLX (AeroLLM)                                                               |
|-------------------|-----------------------------------------------------------------------|-----------------------------------------------------------------------------|
| What happens      | `del layer; torch.cuda.empty_cache()` (or reuse pinned buffer)        | mx.eval + free; possibly LRU if multi-resident                              |
| Tech / method     | VRAM allocator dance; fragmentation risk at high batch sizes          | Simpler on unified; but fragmentation still a risk with LRU                 |
| Knobs             | allocator (native vs jemalloc), empty_cache cadence                   | `stream_resident_blocks`, `stream_eviction` (lru/fifo)                      |
| Batch-amortizable | **YES** — one unload per layer-pass regardless of batch size          | **YES**                                                                     |

### Stage 7 — Sampler / next-token

Logits → token. Cheap. Sometimes done on CPU.

| Aspect            | CUDA (AeroLLM)                                                       | MLX (AeroLLM)                                                           |
|-------------------|---------------------------------------------------------------------|-------------------------------------------------------------------------|
| What happens      | Softmax + sampling (top-k / top-p / temperature)                    | Same, Metal kernels                                                     |
| Tech / method     | Negligible compared to Stages 1–4                                   | Same                                                                    |
| Knobs             | temperature, top_k, top_p, repetition penalty                       | Same                                                                    |
| Batch-amortizable | Fully parallel across batch                                         | Same                                                                    |

---

## The per-token cost equation (for intuition)

For a single prompt through a layer-streamed model:

```
t_token  =  sum over layers of:
              max( load(layer) ,  compute(layer) + kv_ops(layer) )
              + unload(layer)
            + sampler()
```

The `max` captures prefetch overlap: if compute ≥ load, I/O is fully hidden; if compute < load (the common case for consumer hardware), the load dominates.

For **N batched prompts** sharing the same layer pass:

```
t_batch_token_per_prompt  =  sum over layers of:
              max( load(layer) ,  N × compute(layer) + N × kv_ops(layer) )
              + unload(layer)
            + sampler()
/ N
```

As N grows: `load(layer)` stays constant while `N × compute(...)` grows. Eventually compute dominates — that's the **batch-size knee** where adding more prompts stops helping per-token latency and starts hurting it. Finding that knee per-hardware is experiment #1 in `02-batching-strategy.md`.

---

## Timing table (fill in per run)

Format: `median ms / run ± std`. Populate from `lab/data/aerollm-bench.jsonl` and `lab/data/mlx-bench.jsonl`. One row per (model, backend, batch_size, hardware) tuple.

| Stage | CUDA @ 70B-4bit, bs=1, PCIe4 | CUDA @ 70B-4bit, bs=50, PCIe4 | MLX @ 20B-4bit, bs=1, M5-24GB | MLX @ 20B-4bit, bs=8, M5-24GB | MLX @ DS-V3-671B, bs=1, M5-24GB |
|-------|------------------------------|-------------------------------|-------------------------------|-------------------------------|----------------------------------|
| 0. Scheduler                | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |
| 1. Layer load (disk)        | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |
| 2. H2D transfer             | _tbd_ | _tbd_ | n/a | n/a | n/a |
| 3. Prefetch (hidden cost)   | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |
| 4. Compute                  | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |
| 5. KV read/append           | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |
| 6. Unload / evict           | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |
| 7. Sample                   | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |
| **Total t_token (ms)**      | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |
| Tokens/sec                  | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |

Expected first rows from memory (to be verified):

- verdagon bench on 70B bs=1 (consumer laptop, 16 GB): ~35,350 ms/token
- verdagon bench on 70B bs=500: ~4,852 ms/token per prompt
- OGLab gpt-oss-20B-MLX-4bit bs=1 on 24 GB M5: single-digit ms/token (fits in memory — no streaming)
- DeepSeek-V3 671B bs=1 on 24 GB M5: still at Gate-1 status (does-it-load) per `mlx-streaming-plan.md`

---

## What's missing from this map (known gaps)

- **Speculative decoding path.** Stage 4 branches: draft model produces k tokens, target verifies. Adds a Stage 4' for verification pass. Out of scope until single-prompt measurements stabilize; see `github.com/cdarnell/aerollm` optimization #3.
- **MoE router + expert fetch stages.** For DeepSeek-V3 / Kimi K2, Stage 1 splits into "non-expert weights" (always-hot) and "routed experts" (cold-tier fetch). That's its own 3-tier map — see `research/1tb-inference-streaming.md` §4 for the MoE version.
- **Multi-turn / prompt-cache Stage 5'.** When the system prompt is stable, prior KV can be reused. Net zero Stage 4+5 on the prefix. Separate dimension from batching; compounds with it.
- **Energy per stage.** The 2508.06978 study found SSD read energy can be ~80% of per-token energy for disk-streamed MoE. Worth a column if RAPL / IPMI exposes it.
