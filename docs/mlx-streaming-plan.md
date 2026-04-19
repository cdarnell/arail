# MLX Layer-Streaming Plan — running 671B+ on a 24 GB Mac

*Status: DESIGN — not yet implemented.*
*Scope owner: AeroLLM (MLX backend).*
*Sister track: AeroLLM CUDA (see [github.com/cdarnell/aerollm](https://github.com/cdarnell/aerollm)).*

---

## The thesis

OGLab's AeroLLM MLX track claims something simpler and more honest
than beating the clock:

> **A 670B-750B-parameter GLM-class frontier model can respond to
> a real knowledge-inference query on a 24 GB M5 with a 2 TB NVMe.
> Autoresearch finds the knob configuration that makes that possible,
> however long each response takes.**

The win condition is not a tokens/sec number. Speculating on
"we'll go from X minutes to Y minutes" is premature — we haven't
measured X yet, and publishing a target before the measurement is
cart-before-horse. The win condition is binary:

- **Did the model produce an answer?** (status=ok on a frontier row)
- **Is the answer faithful to the model's known quality?** (a
  perplexity or judge-rated sanity check on the output)

Everything downstream — latency trends, knob-driven improvements,
"this sweep cut 22 % off" — only becomes meaningful once that first
`status=ok` frontier row lands. Until then, the honest state of the
world is the `streaming_required:` error row in the dashboard.

This is the "closest thing to AI's god on commodity hardware" bet.
The academic story is not "we won a race." It's "this frontier
model, which needs a B200-class accelerator to fit, ran to
completion on a laptop, and here are the autoresearch-discovered
settings that made it possible."

## Why this isn't a config edit

MLX's native assumption is the whole model fits in unified memory.
`mlx_lm.load(...)` eagerly loads every weight shard, then
`mlx_lm.generate(...)` runs with everything hot. That works for
20 GB models on a 24 GB M5. It does not work for:

| Model                  | 4-bit size | Fits 24 GB M5? | Fits B200 (192 GB)? |
|------------------------|-----------:|:--------------:|:-------------------:|
| gpt-oss-20B            |   11 GB    |      yes       |        yes          |
| Llama 3.1 405B         |  200 GB    |       no       |         no          |
| DeepSeek-V3 671B (MoE) |  335 GB    |       no       |         no          |
| Kimi K2 1T (MoE)       |  500 GB    |       no       |         no          |

To run any of these on a 24 GB box we have to stream layers from the
2 TB NVMe into unified memory, compute, evict — the exact pattern
AeroLLM's CUDA backend implements.

## What AeroLLM does on CUDA (for reference)

1. mmap the weight shards off NVMe
2. For each transformer block, in order:
   - `cudaMemcpyAsync` the block's weights from host RAM → GPU VRAM
   - Run the forward pass for that block (one block's weights hot
     at a time)
   - Free the VRAM slot so the next block can reuse it
3. Per-token: loop through all N blocks, paying the disk→RAM→VRAM
   cost for every block on every decode step.

The latency is dominated by disk bandwidth. NVMe at ~6 GB/s and a
335 GB model means **~56 s of pure weight transfer per forward pass**
if no caching. AeroLLM trims that with a multi-threaded prefetcher,
pinned memory, and 8-bit block-resident quantization.

## What MLX gives us for free (and what it doesn't)

Free:
- Apple's `mmap`-based file loading (`mx.load` on a `.safetensors`
  shard is zero-copy-ish).
- Unified memory means no PCIe transfer. Every byte the weights
  touch is a byte the GPU can address directly.
- Metal Performance Shaders for the compute.

Not free:
- Layer-level lazy loading. `mlx_lm.load` walks the whole safetensors
  index and materializes every parameter up front.
- Eviction. There's no mlx-lm API for "load block N, free block N-1".
- Prefetch. No async disk-read scheduler that overlaps compute on
  block N with weight transfer for block N+1.

These three things are what we have to build.

## The design (load-evict-prefetch loop)

```
┌──────────────────────────────────────────────────────────────────┐
│  2 TB NVMe                                                       │
│   ├── DeepSeek-V3-4bit/ (335 GB across ~170 shards)              │
│   │    block_0.safetensors   block_1.safetensors   …             │
│   └── index.json  (shard → block mapping)                        │
└──────────────────────────────────────────────────────────────────┘
              │  mx.load(shard_path, stream=true)
              ▼
┌──────────────────────────────────────────────────────────────────┐
│  24 GB unified memory                                            │
│   ┌────────────────┬────────────────┬────────────────┐           │
│   │  KV cache       │  block N-1     │  block N (hot) │           │
│   │  (quantized)    │  (evicting)    │                │           │
│   └────────────────┴────────────────┴────────────────┘           │
│                                   │  Metal kernels on block N    │
│                                   ▼                              │
│                           ┌────────────────┐                     │
│                           │  hidden state  │  (4 KB per token)   │
│                           └────────────────┘                     │
└──────────────────────────────────────────────────────────────────┘
```

Data flow per token (greedy decode):

1. Load block 0 from NVMe into unified memory.
2. Run block 0 on the current hidden state.
3. Kick off async prefetch of block 1 (NVMe → memory).
4. Free block 0's memory.
5. Await prefetch completion for block 1, run it.
6. Repeat for all N blocks.
7. Sample next token, loop.

The overlap between "compute block N" and "prefetch block N+1" is
the whole game. Without it, throughput is bounded by disk bandwidth.
With it, throughput is bounded by compute time per block — which is
~10-100× higher on Apple Silicon.

## The modules we need to build

All under `src/oglab/experiments/mlx_streaming/`:

1. **`shard_index.py`** — parse the safetensors index once, produce
   a `ShardMap` keyed by layer number. Pure Python, no MLX deps.
2. **`block_loader.py`** — given a block index, return an `mx.array`
   bag of weights. Supports both eager (testing) and mmap (prod).
   Must use `mx.load(..., return_metadata=True)` to respect quant
   encoding.
3. **`streaming_model.py`** — a thin wrapper around mlx-lm's model
   classes that swaps `forward()` for a block-at-a-time streaming
   implementation. Per-family (DeepSeek V3, Llama, Kimi) because
   block structure differs.
4. **`prefetch.py`** — tiny async worker. Uses a thread + queue,
   not asyncio (mlx-lm is sync). Kicks off `block_loader.load(n+k)`
   while compute runs on block n. Lookahead `k` is a new knob.
5. **`generate.py`** — drop-in replacement for `mlx_lm.generate(...)`
   that dispatches to the streaming forward pass. Same kwargs.

## The new knobs

These extend `config/tuning-mlx.yml`'s `knobs:` block. Each is a
safety-validated tunable the autoresearch agent can sweep.

| Knob                     | Range        | Why it matters                                 |
|--------------------------|--------------|------------------------------------------------|
| `stream_prefetch_k`      | 0–4          | How many blocks ahead to prefetch              |
| `stream_resident_blocks` | 1–8          | How many blocks to keep resident (LRU)         |
| `stream_io_chunk_mb`     | 16–256       | mmap chunk size for disk reads                 |
| `stream_eviction`        | lru / fifo   | Which block to evict first                     |
| `stream_block_quant`     | fp16/8/4-bit | On-the-fly quantize loaded blocks              |
| `stream_expert_cache`    | 1–16         | MoE-only: how many routed experts to keep hot  |

The MoE-specific knob (`stream_expert_cache`) is the one that could
actually deliver the 5 → 3 min leap on DeepSeek-V3. Because only
~37B of 671B params activate per token, with a warm expert cache we
skip most of the weight transfers entirely.

## Measurement plan — prove it works first, speed later

The mistake to avoid is writing down a target latency before the
first measurement exists. We don't know how long a 670B-750B
GLM-class model will take to respond on a 24 GB / 2 TB box; anyone
who claims to, is guessing.

So the plan is staged, with binary gates:

**Gate 1 — does it load at all?**
- Success: `mlx_lm.load(...)` returns a model object without OOM.
- Recorded as: a `status=ok` BenchRun with `tokens_out=0`,
  `total_latency_ms` = load time. No tokens generated yet.
- This alone is a non-trivial result — it says the streaming layer
  works.

**Gate 2 — does it produce one token?**
- Success: a single forward pass completes, one token is sampled.
- Recorded as: `tokens_out=1`, `ttft_ms` populated.
- Latency will be whatever it is. Log it, don't judge it.

**Gate 3 — does it produce a coherent response?**
- Success: `max_tokens=64` generation completes, the output is
  checkable against the model's known quality on a held-out prompt.
- Recorded as: full BenchRun. `decode_tok_per_sec` now has meaning.
- Sanity check: judge the output with a small local model, or
  spot-check by eye. We want to know the weights loaded correctly,
  not a garbled stream.

**Gate 4 — does autoresearch improve on Gate 3?**
- Only *after* Gate 3 lands do we start sweeping knobs and claiming
  improvements.
- The baseline for improvements is whatever Gate 3 recorded.
- "Autoresearch found a 22 % improvement" becomes a claim we can
  actually make at this point, and not before.

Every row in `frontier_baselines` corresponds to a gate number. The
dashboard shows which gate each model is stuck at. That's the
academic artifact — a staged record of an impossible-seeming
inference made possible, with each step evidenced in git.

## What's already in place

- `config/tuning-mlx.yml` declares the frontier model set with
  `streaming_required: true`.
- `tuning.FrontierModel` parses them.
- `mlx_backend.run_frontier_bench` attempts a load, always returns a
  structured BenchRun, tags the failure `streaming_required:` so the
  dashboard renders a clean "waiting on streaming layer" card.
- `ALLOWED_WRITABLE_FILES` extended so the autoresearch loop can
  commit to `tuning-mlx.yml` and `lab/data/mlx-bench.jsonl` — the
  two files a streaming experiment will write.

## What lands next (Phase B)

In order:

1. Download one shard of DeepSeek-V3-4bit to a scratch dir and
   verify `mx.load` can open it without loading the whole thing.
2. Build `shard_index.py` and unit test against the real index.json.
3. Prototype `block_loader.py` with eager mode only.
4. Stand up `streaming_model.py` for DeepSeek-V3 specifically
   (one family first, then generalize).
5. Measure. Record the first "cold" latency number in
   `frontier_baselines`. This is the 5-minute starting point.
6. Add `prefetch.py` and the streaming knobs to `knobs:`.
7. Let autoresearch sweep. Wait for the "5 → 3 min" win.

Each step is gated by tests + the same safety rails: clean tree,
`OGLAB_AUTORESEARCH_ENABLED` flag, commits only to
`autoresearch/*` branches, commits only to whitelisted files.

## Why this is worth building

The layer-streaming pattern is well-established on CUDA. AeroLLM's
MLX backend is how OGLab ports it to Apple Silicon. Doing so on a
24 GB consumer machine —
and proving it with autoresearch-driven measurement rather than
hand-tuning — is both a genuine technical contribution and the exact
kind of story OGLab exists to tell. The logs, metrics, and info
overlays turn a weeks-long performance-engineering effort into
something an academic can actually follow.
