# Vision — `qkz-expert`: a ~1B QuKaiZen-native model that is actually trained

**Date:** 2026-07-24 · **Product:** arail · **Wedge size:** one sprint (Phase A only)
**Gate:** [`SPIKE.md`](./SPIKE.md) — verdict GO. Read it first; it is the reason this
sprint is scoped the way it is.

## User

Charlie, on his own workstation, wanting the everyday lab model to be *his* —
one that already knows aerollm, arail, qukaizen-dac and nucleus — small enough to
sit resident in memory, with anything harder escalating to aeroLLM.

Today his tier 0 is `ai-engineer` (Qwen2.5 **7B**). That is too big for a
permanently-resident everyday model, and it knows nothing about QuKaiZen.

## Problem

Three separate problems, and only the third is new:

1. **Tier 0 is oversized.** A 7B resident model spends memory that the deep tier
   should own. The stated architecture is *1–3B resident, escalate for
   intelligence* — the lab does not currently implement its own design.
2. **The existing "expert" is not real.** `qkz-project-aware-2b-v1.0` claims
   `status: graduated`, three passed cert gates (0.875 / 0.850 / 0.800) and a
   15 MB adapter. The committed adapter is **1210 bytes of JSON with no
   tensors**. Per SPIKE Finding 3, the nucleus trainer silently falls back to
   simulation mode when `mlx_lm` is missing, writing a mock checkpoint plus
   realistic metrics — that is almost certainly what produced it.
3. **Nothing prevents producing a *second* fake expert.** The cert gates passed
   on a simulated artifact once. Without an explicit guard they will again.

## Win condition

Falsifiable, on Charlie's machine, no cloud account. PASS requires ALL of:

- **WC-A — genuinely trained.** A LoRA adapter exists whose file contains **real
  tensors** (asserted: tensor count > 0 and size within an order of magnitude of
  the configured rank), produced by a run where `MLX_AVAILABLE is True`. A run
  that would have been simulated **hard-fails instead of emitting an artifact**.
- **WC-B — measurably QuKaiZen-native.** On ≥10 held-out QuKaiZen questions
  (drawn from real repo content, not authored by the model), the fine-tuned
  model beats the untouched base on a **code-computed** metric. Measured by the
  mini experiment engine from the 2026-07-23 sprint — no model self-scoring.
- **WC-C — it is the resident tier 0.** It loads through ARAIL's registry as the
  `fast` profile, answers in chat, and its footprint is **≤ 3 GB resident**.
- **WC-D — honest provenance.** The shipped spec states the real base, the real
  training corpus, the real adapter size, `license: gemma-terms-of-use`, and
  "Built with Gemma". No Apache-2.0 claim (fixed in this branch), no inflated
  size, no gates claimed that did not run on real tensors.
- **WC-E — reproducible.** A committed run receipt (base id, corpus SHA, config,
  seed, adapter SHA256, host) lets the run be repeated.

**Explicit non-goal for Phase A:** the Ed25519 seal / certifier. See Wedge.

## Wedge

**Phase A only: train the thing, natively, honestly.** Per SPIKE Finding 2, the
nucleus `MLXTrainer` is pure compute with no NATS dependency and `mlx_lm` is
installed — so training needs **no Docker stack at all**. That is the whole
reason this is one sprint.

**IN:**
- Base: **`mlx-community/gemma-4-e2b-it-OptiQ-4bit`** — 1.14B params,
  `text-generation`, mlx library, `license:gemma`, apple-silicon mixed-precision.
  Small enough to stay resident, trains with plain `mlx_lm`, and Gemma-family so
  the speculative option stays open (SPIKE Finding 5).
- Corpus: QuKaiZen repos (aerollm, arail, qukaizen-dac, nucleus), content-hashed.
- Training: `MLXTrainer` LoRA, with the **anti-fabrication guard** as a
  first-class deliverable, not a nicety.
- Eval: held-out QuKaiZen questions scored by the existing mini experiment
  engine (`arail.research.mini_experiments`) — reuse, don't rebuild.
- Register as ARAIL tier 0; honest spec + run receipt.

**OUT (deferred on purpose):**
- **Sealing / the certifier / OrbStack.** Phase B. SPIKE says Docker is merely
  stopped, not broken — so this is deferred by *choice*, to keep Phase A's blast
  radius small, exactly as `2026-07-22-distill-now` pre-committed.
- **Speculative decoding wiring.** See the tension below — it needs a decision
  Phase A's results should inform, not precede.
- Compaction, the "Distill now" button, multi-World, scheduler.

## The tension nobody should discover late

Charlie wants two things that partially conflict:

- **A fine-tuned little expert** (knows QuKaiZen), and
- **a speculative draft** for the big Gemma verifier.

Speculative decoding accepts a draft token when the draft's distribution matches
the target's. **Fine-tuning the draft on QuKaiZen code moves it away from the
target's distribution — which can lower the acceptance rate and give back the
speedup.** The two goals want opposite things from the same weights.

They are separable, and Gemma-4 makes that easy:

| Role | Artifact | Fine-tune it? |
|---|---|---|
| Everyday resident tier 0 | `qkz-expert` (this sprint, ~1.1B) | **Yes** — that's the point |
| Speculative draft for the 26B/31B | untouched small Gemma, or the **12.4M `gemma4_assistant` MTP head** | **No** — keep it distribution-matched |

So: fine-tune for tier 0; leave draft duty to an unmodified artifact. Phase A
does not have to choose, but it must not *assume* one model serves both.

## Disconfirming evidence

Pre-committed. Hit these and we descope rather than rationalize.

1. **`mlx_lm` can't LoRA a 4-bit OptiQ mixed-precision checkpoint.** Mixed
   4/8-bit may not be a supported LoRA target. Spike this on day one against a
   ~20-example corpus **before** building the full corpus. If it fails, fall back
   to a plain `gemma-4-e2b-it-4bit` (or bf16) base — do not fight the quant.
2. **1.1B is too weak to be the everyday model.** If WC-B shows the fine-tune
   does not beat the base, or chat quality is visibly worse than today's
   `ai-engineer`, the honest outcome is: keep the expert as a *specialist* the
   router selects for QuKaiZen questions, and leave general tier 0 alone. Do not
   ship a downgrade and call it a win.
3. **The corpus makes it worse.** Training on raw repo dumps can degrade
   instruction-following (catastrophic forgetting). If held-out *general* prompts
   regress badly, reduce to a curated Q&A corpus rather than raw files.
4. **Resident footprint exceeds 3 GB.** Then it is not the always-resident tier 0
   this architecture wants; re-scope to on-demand.

## Displacement

Saying yes costs: the distill-now seal/compaction chain stays paper for another
cycle; the deferred clean-experience polish waits; aeroLLM GA gates get no time.
Accepted — a real resident expert is the thing Charlie actually asked for twice.

## Recommended next step

**PROCEED to Phase A, conditioned on the day-one LoRA-compatibility spike
(disconfirmer 1).** Prove `mlx_lm` can train a LoRA against the chosen base with
a throwaway 20-example corpus before spending time on corpus construction.

The anti-fabrication guard (WC-A) is not a task to schedule late — it is the
first thing to write, because without it every downstream number is suspect.
