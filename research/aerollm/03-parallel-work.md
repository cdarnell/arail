# 03 — Parallel Work: What's Already Shipped, Where Our Lane Is Clean

*Don't reinvent. But don't assume everything's been done either.*

This doc has two halves:

- **Half A — Inference engines.** People trying to run big models on small machines.
- **Half B — Distillation and synthetic-data techniques.** People turning teacher outputs into better students.

OGLab's product sits at the intersection. No one public (as of April 2026) has combined a layer-streamed frontier teacher with an adversarial-agent distillation swarm on a single consumer box. Each half of the stack has 2–5 serious competitors; the *combination* is the novel lane.

**Note on track-level novelty.** Within Half A, the CUDA lane is already crowded — AeroLLM, KTransformers, vLLM, and llama.cpp all address some version of the problem. The **MLX lane is nearly empty**: SwiftLM is the only published adjacent effort, and it doesn't ship batching or autoresearch. That's why AeroLLM prioritizes MLX — the marginal public-good contribution is higher there, and the engineering risk is real but bounded (the design is explicit in `docs/mlx-streaming-plan.md`). The CUDA track in AeroLLM is not trying to out-invent AeroLLM; it's carrying a proven baseline along so the distillation product works on both consumer-Apple and consumer-NVIDIA hardware.

---

# Half A — Inference engines

## A.1. AeroLLM (upstream) — the reference

**Repo:** `cdarnell/aerollm`
**Status:** active but slower cadence in 2026. Last meaningful optimization PR was Q4 2025.
**What it does:** layer-by-layer streaming on CUDA. Model's weight shards mmap'd from disk, `cudaMemcpyAsync`'d into VRAM block-by-block, forward pass runs one block hot at a time, evicts. Optional 8-bit block-resident quantization.
**What it's known to do well:** squeeze a 405B Llama into a 24 GB consumer GPU. Inference works end-to-end.
**What it doesn't do:**
- No batched inference path in the reference (this is open question #2 — verify). If it's truly single-prompt-per-layer, a ~100-line patch to the forward loop unlocks the batching thesis.
- No MLX/Apple Silicon path.
- No scheduler / queue / continuous-batching abstraction — it's a library, not a server.
- Light on observability — no per-stage timings exposed.

**Where AeroLLM adds value:** multi-threaded prefetch + concurrent-prompt batching inside the Rust core, an MLX backend (no public equivalent today), an autoresearch knob-sweep framework, and per-stage observability. Most of what OGLab ships on top is application code — scheduler, dashboard, benchmark capture.

## A.2. vLLM

**Repo:** `vllm-project/vllm`
**Status:** very active, reference implementation for continuous batching.
**What it does:** PagedAttention + continuous batching + prefix caching. Serves up to thousands of concurrent requests on a single GPU.
**Overlap with us:** enormous on batching *within a fitting-in-VRAM model*. Zero on our problem, because vLLM assumes the model fits in GPU memory. It does not do layer streaming. If you can fit the model, use vLLM; if you can't, vLLM can't help.
**Takeaway:** we steal vLLM's batching shape (continuous batching, prefix caching, sampler independence) but apply it to a *streamed-weight* backend that vLLM doesn't support.

## A.3. SGLang

**Repo:** `sgl-project/sglang`
**Status:** very active. First-class support for structured generation, constrained decoding.
**What it does:** RadixAttention (tree-structured prefix cache), fast structured generation (JSON schema, regex), continuous batching.
**Overlap with us:** RadixAttention is directly useful for distillation — if many seed prompts share a common system prompt, we can cache the KV once. Their structured-generation kernels matter for producing *symbolic* CoT in a parseable format.
**Where we borrow:** prefix-cache design. Structured-output constraints for symbolic CoT.
**Where we don't compete:** like vLLM, SGLang assumes the model fits. Streaming is out of scope for them.

## A.4. KTransformers

**Repo:** `kvcache-ai/ktransformers`
**Status:** very active. The "run big MoE on a consumer box with aggressive CPU/GPU split" engine.
**What it does:** selective GPU offload of hot experts, CPU inference for cold experts, custom kernels for MoE. Reports **4.62–19.74× prefill speedup and 1.25–4.09× decode speedup over llama.cpp** on DeepSeek-V2 / V3 class models.
**This is the most direct competitor to our CUDA track.**
**How it differs from AeroLLM:**
- KTransformers puts *hot* layers/experts on GPU and runs cold ones on CPU. AeroLLM *streams* all layers through GPU sequentially.
- KTransformers is MoE-centric (exploits expert sparsity). AeroLLM is architecture-agnostic.
- KTransformers requires lots of system RAM (the cold experts sit in RAM); AeroLLM works with very little RAM because cold layers sit on disk.
**When KTransformers wins:** 192+ GB RAM, MoE model, moderate generation length.
**When AeroLLM wins:** 24 GB hardware, dense model or cold MoE, willingness to trade latency for fit.
**Our lane:** the consumer extreme end (16–64 GB RAM, 2 TB disk). KTransformers' assumptions break there.

## A.5. llama.cpp + CPU offload

**Repo:** `ggml-org/llama.cpp`
**Status:** reference implementation for everything-CPU inference. Has MoE offload (recently improved).
**What it does:** GGUF format, efficient CPU/GPU split, supports huge models via mmap and lazy loading.
**Reality check:** on a 24 GB M-series Mac, llama.cpp with a 4-bit DeepSeek-V3 is slower than MLX-native for 20B-class models but surprisingly competitive for MoE because the MoE activation pattern plays nicely with its mmap tricks. People *are* running DeepSeek-V3 on Mac Studios via llama.cpp today.
**Overlap with us:** substantial on Apple Silicon. But llama.cpp doesn't have a layer-streaming story — it loads the model once and keeps it resident (even if mmap-lazy). Real frontier models on small boxes are OOM-risky.
**Where we differ:** we deliberately *stream* through disk, which llama.cpp doesn't. For 671B on 24 GB, llama.cpp just OOMs. For models that fit in RAM, llama.cpp is probably better than us because it's had 3 years of optimization.

## A.6. SwiftLM — the closest prior art for MLX streaming

**Paper/blog:** SwiftLM (MLX NVMe streaming, late 2025 / early 2026).
**What it does:** layer streaming on Apple Silicon via NVMe. Reports ~10× speedup on 122B+ MoE models when NVMe read is overlapped with Metal kernel execution.
**This is the single most relevant piece of parallel work to AeroLLM.**
**Overlap:** near-total on the *mechanism* — mmap + async prefetch + Metal compute, exactly what `docs/mlx-streaming-plan.md` describes.
**How we differ:**
- SwiftLM is inference-engine. Our agenda is *distillation product on top of inference*. Different scope.
- SwiftLM reports speedup vs a "no streaming" baseline that doesn't fit on the hardware at all — those numbers are against an impossible baseline. Useful for intuition, not for our throughput-per-watt-per-dollar target.
- SwiftLM appears not to have the autoresearch knob-sweep framework. We do.
- Per the docs (verify when their code is open), they haven't shipped a scheduler for batched prompts over streamed weights. Our batching thesis is orthogonal to SwiftLM's streaming.
**Action:** read their code as soon as it's public. Adopt their prefetch/eviction design if it's cleaner than ours. This is the one project where we should explicitly try to merge efforts rather than re-invent.

## A.7. MoE-specific 2025-2026 papers worth tracking

All of these are candidate ideas for specific knobs, not replacements for our pipeline.

- **Flash-MoE** — fused MoE kernels, reduces kernel-launch overhead. Apply on the compute stage.
- **HybriMoE** (Sun et al., 2025) — hybrid GPU+CPU expert placement with dynamic migration. Overlaps with KTransformers.
- **BlendServe** — batched serving for MoE, exploits expert co-activation patterns. Useful insight for our scheduler.
- **MoE-Gen** (2503.09716) — generative-phase throughput for MoE, expert-batching across prompts.
- **PIPO** (2504.03664) — pipeline-parallel over streamed weights (different scope, same shape).
- **MoE-SpeQ** — speculative expert fetch, pre-fetches likely-to-activate experts based on routing history.
- **DualPath** (2602.21548) — dual-lane (fast + slow) inference, one of many sketches that resemble our "fast draft + slow teacher" idea.
- **Layered Prefill** (2510.08055) — prefill-time layer prefetch optimization. Directly applicable to batched prefill.
- **PreScope** — predicts next-expert activations to warm the cache ahead of the routing decision.

None of these is a drop-in replacement for our pipeline. Several are potential knobs in `config/tuning*.yml`.

## A.8. Where the inference lane is clean

Summary: **layer-streamed inference + batching-as-application-scheduler + MLX port + autoresearch knob-sweep.** No single competitor hits all four. SwiftLM comes closest (streaming + MLX) but lacks batching and autoresearch; KTransformers lacks streaming at our extreme; AeroLLM upstream lacks batching and MLX.

---

# Half B — Distillation and synthetic-data techniques

This is where the novel product value lives. The inference engine is a means; the distilled SLM is the end.

## B.1. Symbolic Chain-of-Thought Distillation (SCoTD)

**Paper:** Li et al., "Symbolic Chain-of-Thought Distillation: Small Models Can Also 'Think' Step-by-Step" — arXiv 2306.14050.
**What it says:** distill a GPT-3-class teacher's CoT rationales into a 125M-parameter student. Student recovers 75+% of teacher accuracy on commonsense QA at 3 % of params. Key move: the CoT traces are *symbolic* (structured into discrete reasoning steps), not free-form text.
**Why it's core to our product:** this is the empirical backing for the "symbolic CoT" part of the vision doc. We're doing the same thing, with a larger teacher, more agentic filtering, and the teacher running locally instead of via API.
**What we add:** the teacher is 671B+, not 175B. The filter is an adversarial swarm, not a single-shot quality check. The teacher runs on-device, not via OpenAI.

## B.2. Orca 2 (and the "Cautious Reasoning" tradition)

**Paper:** Mitra et al., "Orca 2: Teaching Small Language Models How to Reason" — arXiv 2311.11045.
**What it says:** don't just teach the student to imitate the teacher's answers — teach it to *choose* a reasoning strategy (chain-of-thought, step-by-step, direct answer) based on the task. Student learns a meta-policy over reasoning modes.
**Why it's relevant:** Orca 2's data-generation pipeline is a template for ours. They prompt the teacher with carefully-crafted system prompts that elicit *different* reasoning styles on the same problem. The student sees multiple ways to solve each prompt.
**What we add:** Orca 2 used a cloud GPT-4 teacher. We use a local frontier teacher, which means we can experiment with prompt formulations at volume without per-query API cost.

## B.3. Phi series — the synthetic-data scaling playbook

**Papers:** Phi-3 technical report (2404.14219), Phi-4 technical report (2412.08905), Phi-4-Mini-Reasoning (2504.21233).
**What it says:** quality > quantity. A ~10B model trained on carefully curated synthetic data from a frontier teacher beats much larger models trained on web data. Phi-4 matches GPT-4-class performance on some reasoning benchmarks at ~14B params.
**Why it's relevant:** Phi establishes that this approach *works at production scale* — Microsoft is betting real money on the playbook we're replicating. Our differentiator isn't the approach; it's the *access model* (local, cheap, iterable) and the *swarm filtering* (more aggressive quality control than Phi's single-model pipeline).
**What to lift:** Phi-4's quality criteria (reasoning correctness, diversity, difficulty calibration). Their curriculum ordering (easy → hard during training).

## B.4. Orca-AgentInstruct — the agentic data-generation pattern

**Paper:** Mitra et al., "Orca-AgentInstruct: Toward Generative Teaching with Agentic Flows" — arXiv 2407.03502.
**What it says:** use a multi-agent system to *generate* high-quality synthetic instruction data. Content Transformation Agent → Seed Instruction Generator → Instruction Refinement Agent → Response Generator. Pipeline produces ~25M training pairs for Mistral-7B with measurable quality improvements over single-pass generation.
**Why it's core to our product:** this is the public precedent for "agent swarm generates better synthetic data than single-model pass." Our adversarial swarm is a close cousin. Differences: we add red-team adversaries (AgentInstruct is cooperative/refining, we're adversarial/probing), and our teacher is larger.
**What to lift:** their pipeline decomposition (seed → refine → generate → critique) is a sound skeleton to start from.

## B.5. Lion — adversarial distillation via iterative refinement

**Paper:** Jiang et al., "Lion: Adversarial Distillation of Closed-Source Large Language Model" — arXiv 2305.12870.
**What it says:** alternate between (i) teacher and student solving the same hard prompts, (ii) identifying where the student fails, (iii) generating harder variants of those prompts, (iv) re-training on those. The "adversarial" part is that the prompt pool is continuously adversarial to the student's current weak spots.
**Why it's relevant:** this is the closest published work to the "red-team" role of our swarm. Lion uses it for instruction-following; we use it for reasoning trace generation, which is stricter.
**What to lift:** the referee/loop structure. Keep a "hard examples" queue that's disproportionately sampled during training.

## B.6. Generative Adversarial Distillation (GAD)

**Paper:** Oct/Nov 2025 — arXiv 2511.10643.
**What it says:** frame distillation as a GAN-style game. A discriminator tries to tell teacher outputs from student outputs; the student trains against this discriminator as well as against matching the teacher's tokens. The discriminator catches surface-level imitation failures (stylistic collapse) that plain token-matching distillation misses.
**Why it's relevant:** it's a training-time technique rather than a data-generation technique, so it's technically out of scope for our data-generation product — but it's directly compatible. The corpus we ship could feed straight into a GAD-style training run.
**What to lift:** GAD's discriminator feature design is a possible quality-score feature for our corpus curation stage (B.9 below).

## B.7. Mentor-KD

**Paper:** Kang et al., "Mentor-KD: Meta-Learning with Knowledge-Distilled Mentor Networks" — arXiv 2410.09037.
**What it says:** when a weak teacher lacks CoT coverage, train a *mentor* model on the easy examples the teacher can do, then use the mentor to provide CoT supervision for the harder examples.
**Why it's relevant only peripherally:** our teacher is a frontier model with full CoT coverage, so we don't need a mentor. But if we ever use a mid-sized open teacher (say Qwen3-32B) to save inference cost, Mentor-KD becomes the right technique to backfill missing reasoning traces.

## B.8. Agent Distillation

**Paper:** "Agent Distillation: Distilling Agentic Behavior into Small Language Models" — arXiv 2505.17612.
**What it says:** distill not just the text output but the tool-use and multi-step action sequences of an agentic teacher into a smaller student. The student learns to *act*, not just to answer.
**Why it matters if we expand scope:** for an SLM that needs to use tools (search, calc, code execution), Agent Distillation is the relevant technique. Orthogonal to symbolic CoT distillation but combinable.

## B.9. Distribution-Aligned Sequence Distillation

**Paper:** Jan 2026 — arXiv 2601.09088.
**What it says:** standard sequence distillation minimizes KL on teacher-generated sequences, which biases the student toward the teacher's distribution *conditional on its own generations*. Distribution-Aligned variant corrects this with an importance-sampled correction term.
**Why it's relevant:** this is a training-time improvement, out of scope for our corpus generator. But worth flagging to downstream users of the corpus.

## B.10. Critical methods we should NOT adopt naively

- **Generic token-matching KD (Hinton et al. 2015).** Collapses to "imitate the logits" — works for classification, fails for generative reasoning. Our entire thesis is about going past this.
- **Self-Instruct (Wang et al., 2212.10560) without a critic step.** Self-Instruct produces massive synthetic corpora cheaply but with famously poor quality gradients. Combined with a strong filter (our swarm), it's fine; without, it generates noise.
- **Pure RL / GRPO / DPO on unfiltered teacher output.** Any preference-learning signal inherits the teacher's biases and hallucinations unless the preferences themselves come from a separate judge. The swarm is that judge.

## B.11. Where the distillation lane is clean

Summary: **adversarial swarm (not single critic) + local frontier teacher (not API) + symbolic CoT (not free-form) + iterative hard-example mining (Lion-style)**. Each piece has prior art; the combination in one pipeline, running on a consumer box, is new.

---

# Half C — The combination is novel

Concretely: as of April 2026, no public project combines:

1. A frontier-scale (>400B total params) open-weights teacher, running on commodity consumer hardware via layer streaming.
2. Application-layer batching that turns that teacher into a high-throughput offline corpus generator.
3. An adversarial agent swarm filtering the teacher's output.
4. Symbolic CoT elicitation (not free-form text).
5. A measurement-driven autoresearch loop that tunes inference knobs against a downstream distillation objective — not just tokens/sec.

SwiftLM does (1) partly. Phi does (3) and (4) partly, with a cloud teacher. Orca-AgentInstruct does (3) partly, with a cloud teacher. KTransformers does (1) partly, without (2) (3) (4) (5). We are sitting on the corner of a 5-dimensional space where no one has published yet.

Our moat isn't any one of the five; it's that they compound. A batching scheduler is 10× wasted effort without a working streaming engine. A swarm is 10× wasted effort without batching throughput. The autoresearch loop is meaningless without all of the above producing measurable signal. Each piece shipped by itself is underwhelming; together, they tell a coherent product story.

---

## Citations (quick-links)

| Ref                                  | arXiv / URL        | Section |
|--------------------------------------|--------------------|---------|
| AeroLLM                                | github/cdarnell/aerollm | A.1 |
| vLLM                                  | github/vllm-project/vllm | A.2 |
| SGLang                                | github/sgl-project/sglang | A.3 |
| KTransformers                         | github/kvcache-ai/ktransformers | A.4 |
| llama.cpp                             | github/ggml-org/llama.cpp | A.5 |
| SwiftLM                               | swiftlm.ai (check for preprint) | A.6 |
| Flash-MoE                             | 2025 preprint      | A.7 |
| HybriMoE                              | 2025 preprint      | A.7 |
| MoE-Gen                               | 2503.09716         | A.7 |
| PIPO                                  | 2504.03664         | A.7 |
| DualPath                              | 2602.21548         | A.7 |
| Layered Prefill                       | 2510.08055         | A.7 |
| SCoTD                                 | 2306.14050         | B.1 |
| Orca 2                                | 2311.11045         | B.2 |
| Phi-3 technical report                | 2404.14219         | B.3 |
| Phi-4 technical report                | 2412.08905         | B.3 |
| Phi-4-Mini-Reasoning                  | 2504.21233         | B.3 |
| Orca-AgentInstruct                    | 2407.03502         | B.4 |
| Lion                                  | 2305.12870         | B.5 |
| Generative Adversarial Distillation   | 2511.10643         | B.6 |
| Mentor-KD                             | 2410.09037         | B.7 |
| Agent Distillation                    | 2505.17612         | B.8 |
| Distribution-Aligned Seq Distillation | 2601.09088         | B.9 |
| Let's Verify Step by Step             | 2305.20050         | vision doc |
| Self-Instruct                         | 2212.10560         | B.10 |
