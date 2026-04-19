# 02 — Batching Strategy: the Throughput Engine Behind the Distillation Product

*The "how" of the economic foundation in [`00-product-vision.md`](./00-product-vision.md).*

The thesis: a layer-streamed inference engine is a terrible chat engine and an excellent **offline training-pair factory**. For distillation we don't care about time-to-first-token — we care about training-examples-per-day-per-machine. That reframes every design decision.

---

## The one-paragraph motivation

When a 671B frontier model is streamed from NVMe, each decode step loads ~335 GB of 4-bit weights off disk, runs ~37B worth of compute (MoE active params), then evicts. The disk-load cost is ~56 s of pure bandwidth at 6 GB/s NVMe. That cost is *fixed per layer pass* — it doesn't care how many prompts you're running. If you run one prompt, you pay 56 s to get one token. If you run 500 prompts, you pay 56 s to get 500 tokens. **This is why batching is a throughput multiplier, not a latency hack.** The single-prompt number is a distraction; the aggregate number is what funds the distillation corpus.

---

## The math, stated clearly

Let:
- `T_load` = time to load one layer's weights from disk → accessible memory (seconds)
- `T_compute(N)` = time to run the forward pass for that layer on a batch of N prompts (seconds)
- `L` = number of transformer layers
- `N` = batch size (number of prompts flowing through the layer pass simultaneously)

Time per token, per prompt, at batch N:

```
time_per_token_per_prompt(N)  =  L × (T_load + T_compute(N))  /  N
                              =  (L × T_load) / N   +   (L × T_compute(N)) / N
```

Two limits:
- **Load-bound regime** (small N): the first term dominates. Doubling N roughly halves per-token time. This is the verdagon.dev 7.3× win.
- **Compute-bound regime** (large N): `T_compute(N)` grows roughly linearly with N (more prompts = more matmuls), so `T_compute(N)/N` flattens. Gains stop.

The sweet spot is the batch size where `T_load ≈ T_compute(N) × some_constant`, i.e., disk and compute costs are balanced. That's the knee of the curve in the infographic. For the 70B verdagon data, the knee is somewhere between N=50 (5.32 s/token) and N=500 (4.85 s/token) — close to saturated by 500. Only a 10 % further gain from 50 → 500, suggesting the knee is nearer to 50.

**What that means for distillation corpus generation:**
- We want the **largest N that fits in memory**, even if tokens/sec gains are tiny past the knee — because we have no latency penalty and every extra prompt is another free training example out of the same layer pass.
- Unless memory runs out. Then N is bounded by the KV cache + activations per prompt, not by the curve.

---

## Aggregate throughput (the number that actually matters)

The distillation-workload metric isn't "seconds per token for one prompt." It's **total tokens out of the pipe per unit time**:

```
aggregate_tokens_per_sec(N)  =  N  /  (L × (T_load + T_compute(N)))
```

Holding `T_load` fixed at 56 s (671B 4-bit on NVMe) and assuming `T_compute(N)` scales roughly as `0.01 × N` seconds per layer on an M5-class GPU at the active-params size:

| N    | per-layer time | layers × time (L=61 for DSv3)| tokens/sec aggregate |
|-----:|---------------:|-----------------------------:|---------------------:|
|   1  | 56.01 s        | 3417 s                       | 0.00029              |
|  10  | 56.10 s        | 3422 s                       | 0.0029               |
|  50  | 56.50 s        | 3447 s                       | 0.0145               |
| 100  | 57.00 s        | 3477 s                       | 0.0288               |
| 500  | 61.00 s        | 3721 s                       | 0.1343               |
|1000  | 66.00 s        | 4026 s                       | 0.2484               |

Numbers are illustrative — real T_compute for DeepSeek-V3 active experts is the measurement task, not a guess. **The shape is what matters: aggregate throughput climbs almost linearly in N until compute starts to bite, which for disk-streamed setups is very late.**

Per-day at N=500 and 0.13 tokens/sec aggregate: ~11k teacher tokens/day. Per-day at N=1000: ~21k. At ~500 tokens per training example that's 22–42 distillation examples/day at these conservative numbers, or 170× better than N=1. Tune T_load down with a better NVMe, or find real T_compute is lower than assumed, and these numbers improve 5–10×.

**The day this folder becomes real** is the day we replace the table above with measured numbers.

---

## The memory wall (what caps N on each hardware tier)

Each prompt in the batch carries:
- **KV cache** — roughly `2 × num_layers × d_model × context_len × dtype_size` bytes. For DeepSeek-V3 at context 4096, fp16: ~3.8 GB *per prompt*. At 4-bit quantized KV: ~1 GB/prompt. At 2-bit: ~0.5 GB/prompt.
- **Activations** — forward pass intermediate state, roughly `d_model × context_len × dtype_size × 4 layers-of-working-set`. Tens of MB per prompt, negligible at the scale of KV cache.
- **Shared weights** — fixed at one layer's worth, independent of N. For DSv3 at 4-bit that's ~5.5 GB resident.

Ceilings for DeepSeek-V3 with fp16 KV cache, context 4096:

| Hardware               | Usable RAM for batch | Max N (fp16 KV) | Max N (4-bit KV) |
|------------------------|---------------------:|----------------:|-----------------:|
| M5 24 GB unified       | ~15 GB               |              3  |             14   |
| M-series 96 GB unified | ~85 GB               |             22  |             83   |
| Linux 512 GB + 24 GB GPU | ~500 GB host       |            130  |            500   |
| Studio 512 GB unified  | ~500 GB              |            130  |            500   |

**This is the single biggest reason `kv_bits` is the top-ranked tunable knob in `config/tuning-mlx.yml`.** At 24 GB and fp16 we're stuck at N=3; at 4-bit KV we unlock batch 14, which is 4.7× more teacher tokens per unit time *for the same hardware*. Every quality-check sweep on `kv_bits` is actually a batch-size sweep in disguise.

(Separately, longer contexts crush N faster than anything else — each doubled context is another 2× KV cache per prompt. For CoT distillation the typical prompt + reasoning + answer is 1–4k tokens, so we're not pushed to the long-context regime, but if we ever distill from long-doc reasoning we'll feel it.)

---

## The four scheduler shapes, and why we pick one

There are four obvious scheduler designs for "batch N prompts through a streamed-weight model":

### (a) Static-batch offline ← this is us

All N prompts for a run are queued up front. The scheduler picks the largest N that fits, runs them through the layer pass in lockstep, all N finish together, all N start together. Maximum throughput, zero adaptivity, zero latency considerations.

For distillation this is the right answer. We have millions of seed prompts. We can fill a batch completely. There's no first-come-first-served pressure.

### (b) Continuous batching (vLLM / SGLang style)

Prompts stream in over time. The scheduler keeps the GPU busy by dropping completed prompts from the batch and inserting new ones *mid-layer-pass*. Great for chat workloads, hard to justify for streamed weights because the layer-load cost is the same regardless of batch churn.

Skip for v1. Interesting for v2 if we ever want a long-running teacher service.

### (c) Variable-length adaptive batching

Group prompts by expected output length (short answers together, long CoTs together). Prevents the "one slow prompt blocks everyone" problem of static batching. Worth it if output length varies by 5×+ within a domain.

For the first distillation runs, skip — prompt templates should already control output length.

### (d) Dynamic micro-batch over memory headroom

As memory fills up during generation (KV cache grows), temporarily split N into smaller sub-batches. Complex, trades throughput for the ability to start with a higher N. Probably not worth the complexity budget.

**The v1 scheduler is (a) — static offline batching at the max-N that fits.** Built as an application layer on top of AeroLLM/AeroLLM, no internal changes needed if AeroLLM's forward loop already accepts batched input tensors.

---

## The first four experiments to run

Each one is a row in `04-measurement-log.md`. Each produces a number that replaces a guess in `00-product-vision.md`. **Ordered MLX-first**, because that's the primary track.

### Experiment 1 — "Where is the batch knee on MLX for gpt-oss-20B?" (MLX)

- **Hypothesis:** With all weights in unified memory (no streaming), the knee is at low N because `T_load` is near-zero. This is the clean-signal baseline before we add the disk-streaming variable.
- **Setup:** MLX, the `research_model` from `config/tuning-mlx.yml` (gpt-oss-20B-MLX-4bit). Batch sizes {1, 2, 4, 8, 16}. Fix `kv_bits=fp16` for clean signal.
- **Metric:** tokens/sec aggregate. Memory at peak.
- **Expected:** flatter curve than the verdagon.dev data, saturates by N=4. This tells us how much of the batching win is "avoiding disk" vs "amortizing any fixed cost" — which we need to know before interpreting streamed-model results.

### Experiment 2 — "What does `kv_bits` really buy us in batch terms?" (MLX)

- **Hypothesis:** `kv_bits=4bit` unlocks ~4× larger max N on the 24 GB M5 with no measurable quality hit at context 4096.
- **Setup:** MLX, gpt-oss-20B, each `kv_bits ∈ {fp16, 8bit, 4bit}`. For each, binary-search the max N that doesn't OOM.
- **Metric:** (max_N, tokens/sec aggregate, held-out perplexity) triple.
- **Stop if:** perplexity at 4bit jumps >5 % vs fp16 — then 4bit is off the table for distillation corpus generation, and the batching story is worse.
- **Why it matters:** this knob is the memory-wall argument made concrete. Until we measure it, the 4× max-N claim in `00-product-vision.md` is a guess.

### Experiment 3 — "Can we produce ONE valid training example end-to-end?" (MLX)

- **Setup:** Seed prompt → MLX teacher (gpt-oss-20B for now — streamed frontier model later) → swarm filter (Qwen3-8B-4bit: critic pass, judge pass) → corpus writer. All synchronous, no batching yet.
- **Metric:** does a `(prompt, rationale, answer)` triple land in the output corpus with swarm-filter logs attached? Binary.
- **Why it's essential:** before we scale the inference engine, we have to know the pipeline *works* end-to-end. The worst outcome is a month of batching optimization on a teacher whose output the downstream stages reject. This experiment is cheap — it doesn't need streaming, doesn't need a frontier model, doesn't need large batches.

### Experiment 4 — "Does the verdagon curve reproduce on CUDA?" (CUDA reference)

- **Hypothesis:** On a 70B dense model with AeroLLM reference layer streaming, we see the same shape the verdagon.dev blog reported (near-linear tokens/sec in N, flattening past the knee).
- **Setup:** CUDA path, the AeroLLM runtime + application-layer batching scheduler, Llama 70B 4-bit. Batch sizes {1, 5, 10, 20, 50, 100}. Fixed prompt, 64-token greedy decode.
- **Metric:** tokens/sec aggregate at each N. Plot on log-N axis.
- **Kill criterion:** if aggregate tokens/sec plateaus before N=10, AeroLLM's forward loop isn't actually batching internally and we know where to patch.
- **Why it's #4 and not #1:** CUDA is the reference track, not the primary track. This experiment validates the batching scheduler shape we *also* use on MLX, and gives us a sanity-check baseline for the economic claims in `00-product-vision.md`. It does not block anything on the MLX track.

After these four land, the next round is "sweep the same grid on DeepSeek-V3 via the MLX streaming layer," assuming streaming is working by then (gated on `docs/mlx-streaming-plan.md` Phase B).

---

## Things to nail down before the first real scale run

Not experiments — checklist items. These are where batching implementations routinely break:

- **Padding strategy.** Varying prompt lengths in a batch require either padding to max-length (waste compute) or ragged-batch kernels (not always supported). Pick: pad-to-bucket (group prompts by 512-token bucket).
- **Sampler independence.** Each prompt in the batch must have its own RNG state and its own sampler config. Cache-bleed between prompts = garbage corpus.
- **KV cache layout.** Each prompt needs its own cache slice. If AeroLLM/AeroLLM's current implementation has a singleton cache, we can't batch — period. This is open question #2 from the README.
- **Stopping condition per prompt.** Prompts hit `eos_token` at different times. We either (i) mask finished prompts and keep them in the batch as dead weight until all finish, (ii) swap in a new queued prompt mid-batch (continuous batching). For v1, accept the waste of (i).
- **Error isolation.** One prompt hitting a numerical NaN shouldn't kill the whole batch.

All of these are small independent issues, but any one of them, missed, means the first batched run produces silently-corrupted training data. The adversarial swarm is supposed to catch garbage, but that's a safety net, not a strategy. Get the plumbing right.

---

## How this connects back to the product

Every factor-of-2 we pull out of the aggregate-tokens-per-sec curve doubles the size of the distillation corpus per unit time. At a conservative 10k training examples/day/machine today, a 4× from `kv_bits=4bit` plus 2× from the right batch-scheduler shape gets us to 80k/day. That's a 100k-example domain-specific corpus in under 2 days on a laptop — which, per the Phi-4 data, is enough to produce a strong task-specific student.

The batching work is not an infrastructure project. It's **the product's unit economics.**
