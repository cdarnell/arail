# AirLLM Fork & Innovate Guide

OGLab's "Deep model" path runs through
[AirLLM](https://github.com/lyogavin/airllm) — layer-by-layer
streaming inference that fits frontier-scale models in tiny RAM.
It's Apache 2.0, actively maintained, and has obvious optimization
headroom. This guide is the recipe for forking it, iterating on your
own research, and wiring your fork back into your OGLab in one env
var.

## The question driving this

> Can I make AirLLM noticeably faster on my hardware?

If the answer is yes, you learn the internals of modern LLM
inference, you contribute back to an open project, and you get
frontier-class intelligence on a laptop at speeds that don't test
your patience. If the answer is no, you've still built a measurement
rig that tells you exactly where the bottlenecks are.

## Fork in 60 seconds

```bash
# 1. Fork + clone. Either works; gh is nicer.
gh repo fork lyogavin/airllm --clone --remote
cd airllm

# (Or plain git:)
# git clone https://github.com/lyogavin/airllm.git
# cd airllm
# git remote rename origin upstream
# gh repo create yourname/airllm --public --source=. --remote=origin
# git push -u origin main
```

## Wire your fork into OGLab

One line in `.env`:

```bash
AIRLLM_PACKAGE=git+https://github.com/yourname/airllm@main
```

Then:

```bash
./oglab setup      # reinstalls airllm from your git URL
./oglab restart    # portal picks up the new package
```

That's it. Dashboard's Deep toggle now routes through your fork.
Edit code on the fork → commit → `./oglab setup && ./oglab restart`
to pick up changes. When you want a pinned version instead of `@main`,
swap the suffix: `@v0.3-speculative` or `@commit-sha`.

## Optimization candidates

Graded by estimated effort / impact ratio. Pick one per research
goal — trying to ship all five at once is how forks die.

### 1. Layer prefetch (high impact, moderate effort)

**Observation.** AirLLM's tight loop is:
```
for layer in model.layers:
    layer.load_from_disk()        # blocks on I/O
    hidden = layer.forward(hidden)
    layer.unload()
```

Disk I/O for layer N+1 could start while layer N is computing. A
double-buffered load/compute pipeline hides most of the I/O cost.

**Measured benefit (rough).** 15-40% throughput on NVMe SSDs where
layer load is ≥ compute time. Less on ultra-fast disks where
compute dominates.

**Files to touch.** `airllm/airllm_llama_mlx.py` (or equivalent) —
wrap the layer iterator in a prefetcher, one `asyncio.to_thread`
per next layer.

### 2. Persistent KV cache (high impact, high effort)

**Observation.** Every message in a conversation re-runs the entire
prompt context through all N layers. In chat, the prompt grows
monotonically — layers 0-(M-1) produced the same KV values as last
turn. If we cache the per-layer K/V tensors on disk keyed by (prompt
hash, layer index), follow-up messages skip most of the work.

**Measured benefit.** 3-10× speedup on conversational use cases
where the user is iterating on the same thread. Near-zero benefit
on single-shot queries.

**Files to touch.** Add a `lab/data/airllm-kv-cache/` store +
layer-aware hashing. Evict stale entries with an LRU ~100 GB cap.

### 3. Speculative decoding with the fast SLM (very high impact, hard)

**Observation.** You already have a fast 8B model loaded in RAM
(MLX/Qwen3-8B). It can generate 8-16 draft tokens at 60 t/s.
Passing those tokens through AirLLM in parallel validates N tokens
per layer-pass instead of 1 — the deep model does one pass to
"accept" or "reject" the draft.

**Measured benefit.** 3-5× effective throughput on code + natural
language where the small model gets most tokens right.

**Files to touch.** New `airllm/speculate.py` that wraps the slow
backend; a "draft client" config that points at OGLab's fast model
via HTTP. OGLab's existing router handles the small model side.

### 4. Mixed-precision per-layer (moderate impact, easy)

**Observation.** Not all layers are equally sensitive to
quantization. Attention layers typically need 4-bit for quality;
FFN layers often drop to 2-bit without measurable loss.

**Measured benefit.** 30-50% smaller on-disk footprint, which
translates directly to faster layer loads. Same quality.

**Files to touch.** Extend the compression config to accept
per-layer quantization. Pick thresholds by running an A/B eval on
the validation metric in `lab/pkb/research/prepare.py`.

### 5. Chunked flash-attention for streamed layers (hard, high impact at long contexts)

**Observation.** AirLLM streams one layer at a time but runs
standard attention inside each layer. At long contexts (32K+), the
attention pass itself dominates the per-layer time. Flash-attention-
style tiling would help — but the layer lifecycle makes the kernel
integration non-trivial.

**Measured benefit.** 2-4× on long contexts. Near-zero on short.

**Files to touch.** A CUDA or MLX kernel inside the layer forward
pass. Hard.

## Measurement baseline

OGLab captures every deep-model call to `lab/data/airllm-bench.jsonl`
with model name, latency, tokens out, and hardware. Before you
touch a single line of AirLLM, send 5-10 messages through your
current setup to establish a **baseline**:

```bash
# Nuke any existing bench data
rm lab/data/airllm-bench.jsonl

# Then send messages via the dashboard Deep toggle...

# ...and check the numbers:
curl -s http://127.0.0.1:8080/api/airllm/bench | jq
```

The dashboard's Frontier chip shows "Measured on your hardware"
once there's bench data. Every optimization iteration should show
up in those numbers; if it doesn't, the change didn't help.

## Suggested research goal

Paste this into the OGLab dashboard's Goal box:

> Optimize AirLLM's tokens-per-minute throughput on
> Qwen3-235B-A22B running on my current hardware. Measure baseline,
> implement layer prefetch (optimization #1 from the fork guide),
> compare before/after on at least 5 runs each. Ship a PR upstream
> if the improvement is ≥ 20%.

The researcher agent will decompose this into hypotheses + experiments
+ reports. Every experiment's measurements land in the PKB; the wiki
indexes them; you end up with a repro'd optimization study, not just
a one-shot "it felt faster" claim.

## Contribute back

Once a fork-level change proves itself on your lab:

1. Isolate it from any OGLab-specific glue into a clean branch.
2. Open a PR against `lyogavin/airllm` with before/after numbers
   from `airllm-bench.jsonl` — concrete benchmarks + hardware
   specs beat hand-wavy "faster on my machine" by a mile.
3. Keep the broader experimental work in your fork.

The right cadence is one upstream PR per validated optimization;
everything else lives on your fork until it earns its upstream slot.

## When to stop forking and just contribute

If your changes are small, isolated bug fixes or API additions —
skip the fork entirely. Clone upstream, branch, PR. Forking is for
when you want sustained velocity without review overhead, a
distinctive experimental axis, or your own release cadence.

Three signs you should be doing the fork instead of upstream PRs:
- You've submitted 3+ PRs that are all "optimization attempts" and
  the maintainer wants a coherent design doc before merging.
- You're combining changes that each require the others (layer
  prefetch assumes mixed-precision, KV cache assumes prefetch).
- Your research generates 10+ branches of "what if" that most other
  users won't care about.

If none of those apply, just PR upstream and save yourself the
maintenance burden.
