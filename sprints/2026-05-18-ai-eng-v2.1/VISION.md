# Vision: ai-eng v2.1 as default + AeroLLM maximus secondary lift

**Date:** 2026-05-18
**Product:** arail
**Wedge size:** one sprint

## User

Two concrete personas converge on this sprint:

1. **Clean-machine ARAIL installer on Apple Silicon (M-series, 32–64 GB RAM).** Has just cloned the repo, runs `./arailctl setup` for the first time, expects the advertised v1.0.0 promise: "ai-eng is the only model that auto-installs and it works first try." Today they get a yellow "falling back to qwen2.5:7b preview base — re-run setup once the 3B weights land" warning. They read this as "the project shipped half-finished" — and the README's tier table corroborates that read because it still hedges.

2. **Existing maximus upgrader on a 96+ GB Apple Silicon workstation.** Runs `./arailctl upgrade maximus` expecting an AeroLLM-backed frontier-scale companion to the lab. Today they get a 7B placeholder wired into the deep-mode slot because v1.0.0 punted on choosing AeroLLM's secondary. The Compute Source pivot promises "frontier-scale" and the registered model contradicts it.

Both users experience the same defect: the lab's "default" surface lies about what's underneath.

## Problem

The v1.0.0 setup hedges in two places that should be load-bearing:

- The 3B default is a **persona shim over a 7B base**, not actual fine-tuned weights. Every clean install fires a warning that primes the user to distrust the tier promise. The QuKaiZen LoRA at `qukaizen/qkz-opus4.7-aieng-3b-v2.1-adapter` finally exists; setup.sh has been probing for the canonical tag since v1.0.0; the gap is now bridgeable.
- The maximus deep-mode secondary is the same 7B value as minimalist (`Qwen2.5-7B-Instruct-4bit`). AeroLLM's whole reason for being in maximus is to run models that don't fit memory-resident; wiring a 7B into the slot is theater. AeroLLM's 19/19 golden gates cover Qwen2.5 up to 72B, so we have a proven option sitting unwired.

Underlying pain: ARAIL's promise of "feels like a modern AI lab" (per the pluggable-provider thesis in MEMORY) breaks the moment the user reads setup output. Trust leaks at the first prompt.

## Win condition

Three measurable thresholds, pre-committed:

1. **Setup-on-clean-machine:** a fresh `./arailctl setup` on this Apple Silicon dev box completes with zero yellow warnings from the ai-eng install block. `ollama show ai-eng` reports a v2.1-stamped SYSTEM and a base size matching the merged GGUF (not the 4.7 GB qwen2.5:7b base).
2. **Bench gate:** the merged model (whichever of Candidate A 4-bit-fused or Candidate B bf16-merged wins) is **≥ baseline Qwen2.5-3B-Instruct** on the 12-prompt + 50-question MMLU sample bench (within 3pp tolerance), and **strictly beats `qwen2.5:7b`-with-persona on AI-engineering prompts** in the 5-prompt side-by-side. If it doesn't beat the 7B-persona on at least 3 of 5 AI-eng prompts, we have shipped a regression dressed as an upgrade.
3. **Maximus tier coherence:** `./arailctl upgrade maximus` resolves `AEROLLM_MODEL_MAX_ID` to `mlx-community/Qwen2.5-72B-Instruct-4bit` in the rendered `.env`; `arailctl benchmark_models` registers it; the model is family-consistent with the 3B default (same tokenizer, same prompt format).

Witness signal: the next ARAIL installer (the user themselves, on a fresh worktree this week) does not see a fallback warning and does not need to re-run setup.

## Wedge

The three-phase rollout in the source plan is already the minimum viable wedge — there is no smaller test of the hypothesis that doesn't either skip the bench (unsafe) or skip publish (doesn't close the user-visible warning).

The smallest committable unit is **Phase 1 alone**: build both candidates locally, run the bench, write `models/ai-eng/BENCH-v2.1.md`. If the bench fails, the sprint shelves before any irreversible HF/Ollama push. Phases 2 and 3 are gated on a green Phase 1.

Runnable entirely on the user's own Apple Silicon machine, no cloud account needed — matches the QuKaiZen wedge profile.

## Disconfirming evidence

Pre-committed shelve signals:

- **Bench regression:** Candidate B (bf16 merged) drops >3pp vs Candidate A (4-bit fused) on the 50-question MMLU sample AND Candidate A itself fails to match plain Qwen2.5-3B-Instruct baseline. Interpretation: the LoRA was trained at low enough rank that the merge is lossy in both formats, and we are shipping a vanity rebrand. Shelve the swap, keep the persona shim, and escalate back to QuKaiZen for a retrain.
- **License/training-intent unresolved at D1 checkpoint:** if the QuKaiZen Project Nucleus owner cannot specify a license and a one-paragraph training-data summary for the published model card, do not push to HF. Defer Phase 2 until documented.
- **72B doesn't load on the dev box during verification (Phase 4 step 3):** if registration succeeds but a single smoke inference OOMs on this 96 GB machine, the 72B pick is wrong for the realistic maximus user envelope. Fall back to keeping Llama-3.1-70B (already proven, already wired) and revisit family-symmetry later.

## Displacement

Honest accounting:

- **Other v1.0.0 model swaps** — none currently queued, so cost is zero this sprint, but this sprint sets the precedent for how a default-model swap happens (build → bench → publish → wire). Future swaps inherit this template, which is a small tax on velocity for a large gain in safety.
- **Future LoRA versions (v2.2+)** — explicitly *not blocked* by this sprint. The build scripts produced in Phase 1 (`scripts/build_ai_eng.sh`, `scripts/bench_ai_eng.py`) are reusable. The next adapter rev runs the same pipeline.
- **Expanded provider catalog work** — the pluggable-provider thesis in MEMORY wants more Compute Source options. This sprint touches the default-model surface, not the provider pivot UI; the two streams are independent. No displacement.
- **paperagents-gated surfaces** — explicitly out of scope; SPRINT.md already flags them frozen.

Real opportunity cost: ~1 sprint of the user's calendar time and ~30 GB of dev-box disk for build artifacts. Both are bounded and recoverable.

## Recommended next step

**Proceed to `/architect` design mode with this VISION.md as the spec.**

The wedge is well-sized, the disconfirming signals are pre-committed, and the source plan has already done the file-level archaeology the architect will need. Three risks the architect must design around in ARCHITECTURE.md:

1. **Base-mismatch quality risk on Candidate B.** The LoRA was trained against 4-bit MLX projections; merging into bf16 is not bit-identical. The architecture for `scripts/bench_ai_eng.py` must be paranoid about this — fixed seeds, identical sampling params across candidates, a published prompt list (gating decision D4), and the 3pp gate measured against a baseline, not just A-vs-B. Failure-mode grace: if the bench is ambiguous, ship A.
2. **Setup-on-clean-machine failure-mode grace.** The fallback branch in setup.sh stays in place but its copy changes from "expected, re-run later" to "registry/network failure, retry." The architect must specify the exact triggers that send a user down the fallback path post-publish (Ollama registry 5xx? auth? offline?) and ensure each is logged distinctly. The first-paint-loading-signals MEMORY rule applies: don't go silent if the pull stalls.
3. **Security + onboarding clarity at the publish boundary.** Phase 2 pushes to two external registries (HF, Ollama) under the `qukaizen` org. Credentials handling, license-decision capture (D1), and the user-gated "yes, publish now" prompt (D3) need a documented authority chain in ARCHITECTURE.md so the builder cannot accidentally push without consent. ARAIL's security gating is about *runs on others' machines*; here it extends to *publishes under our org name* — same principle.

ARAIL gating rubric touchpoints: **setup-on-clean-machine** (primary win), **onboarding clarity** (warning copy + README hedge removal), **failure-mode grace** (fallback branch repurpose), **security** (publish authority + secrets), **Buddy quality** (downstream: a stronger default base lifts every Buddy interaction, but is not directly tested this sprint — call out as a follow-up bench in a later retro).
