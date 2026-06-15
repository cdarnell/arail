# Vision: ARAIL Two-Tier Model Architecture

**Date:** 2026-06-14
**Product:** arail
**Wedge size:** one sprint

---

## STOP — the task's model choices contradict shipped reality

Before answering the six questions, I have to challenge the premise, because
this is exactly the kind of decision users "live with after deployment" and
the task itself flags it as critical with "no regrets."

The task asks me to bless:

- **Minimalist:** TinyLlama 1.1B
- **Maximus:** Mistral 7B-Q2 (2.2 GB) via AeroLLM layer-streaming

But `arail/CLAUDE.md` (v1.1, the source of truth in-repo) already ships a
*different* two-tier setup:

- **Minimalist:** `llama-ai-eng` — Llama-3.2-1B-Instruct, ~0.9 GB, runs on 16 GB.
  Auto-installs on a clean machine via `ollama pull llama3.2:1b` +
  `ollama create`. No uploaded artifact required.
- **Maximus deep:** `ai-engineer` — Qwen2.5-7B-Instruct, Apache-2.0, offered
  (not forced) on maximus setup. AeroLLM is the deep-mode backend; CUDA falls
  back to AirLLM with a notice.

These are not cosmetic differences. Three of them would produce real regret:

1. **TinyLlama 1.1B vs Llama-3.2-1B.** TinyLlama is a 2023-era 3T-token model;
   Llama-3.2-1B-Instruct is materially stronger on instruction-following and
   reasoning at the same size class and same ~0.9 GB footprint. For the default
   tier whose whole job is "trustworthy, never embarrasses itself offline,"
   downgrading from Llama-3.2-1B to TinyLlama is a regression, not a choice.
   **Recommendation: keep Llama-3.2-1B as default.**

2. **Mistral 7B-Q2 vs Qwen2.5-7B.** Q2 quantization (2-bit) is the aggressive
   end — it visibly degrades reasoning quality, which is the *entire value
   prop* of the maximus "deep reasoning" tier. Shipping a 2-bit model as the
   thing users turn on *for* reasoning is self-defeating. Qwen2.5-7B at a
   saner quant (Q4_K_M / Q5) is both stronger and the already-chosen lineage.
   **Recommendation: keep Qwen2.5-7B; if a smaller artifact is needed, pick
   Q4, not Q2.**

3. **Licensing.** Mistral 7B is Apache-2.0 (fine), but the repo's
   already-decided posture is Qwen2.5-7B Apache-2.0 for the deep persona
   *specifically because* the "hide-the-base" rule only applies to the
   Apache lineage, while Llama requires disclosure. Swapping in Mistral
   re-opens a settled question for no gain.

The win condition below is written for the **repo's actual model choices**
(Llama-3.2-1B + Qwen2.5-7B), and treats the task's TinyLlama/Mistral-Q2
proposal as a hypothesis I am rejecting on quality and consistency grounds.
If the user has a reason to override (e.g. a specific footprint ceiling that
0.9 GB / a Q4 7B can't meet), that reason needs to be stated — "smaller is
better" is not a reason when the smaller model can't do the job.

---

## User

A developer working on a QuKaiZen project (aerollm, nucleus, or their own
fork of ARAIL) who clones ARAIL onto a 16 GB Apple-Silicon or Linux laptop,
runs `./arailctl setup && ./arailctl start`, and wants a lab partner (Buddy)
and an autoresearch loop that work **offline on first run with zero model
config**. They understand tradeoffs but should not have to make a model
decision to get value. A subset of them later hit a reasoning wall on the
1B model — a multi-step refactor, a research-plan critique — and want to
flip to a stronger local model without leaving airgapped mode.

## Problem

Two distinct pains, one per tier:

- **Minimalist:** "I just cloned a research lab and I want it to *work*, now,
  offline, without me picking a model or burning 10 GB." Today the failure
  mode of getting this wrong is either (a) too-slow/too-heavy default that
  fails on 16 GB, or (b) a model so weak Buddy gives visibly dumb answers and
  the user loses trust in the whole lab on first contact.
- **Maximus:** "The 1B model can't reason through this; I want real local
  depth without sending my code to a cloud." The pain if we get this wrong:
  the "deep" tier feels no better than the default (Q2 degradation), so the
  upgrade was pointless — or it OOMs/streams so slowly it's unusable.

The requested feature ("two-tier models") is the solution; the underlying
problem is **first-run trust (minimalist) and a credible offline ceiling
(maximus)**.

## Win condition

Pre-committed, measurable thresholds. All on a 16 GB M-series laptop, airgapped.

**Minimalist (default, Llama-3.2-1B):**
- Clean-machine `./arailctl setup` to first Buddy token: **< 10 min** including
  model pull on a 50 Mbps link; **zero** model-selection prompts in the default
  path.
- Buddy first-response latency: **time-to-first-token < 2 s**, full short reply
  **< 8 s**.
- Trust bar: on a fixed 10-prompt smoke set (lab-task questions, not trivia),
  **≥ 8/10** answers are coherent and on-task as judged by the QA persona. This
  is the "doesn't embarrass itself" gate.

**Maximus (deep, Qwen2.5-7B at Q4_K_M or better):**
- Enabling deep mode is **one command** (`./arailctl upgrade maximus`) and the
  deep persona is **opt-in, never auto-forced**.
- On the same 10-prompt set plus 5 multi-step reasoning prompts, the deep model
  **beats minimalist on ≥ 4/5** reasoning prompts (else the tier is pointless).
- Runs in airgapped mode on 16 GB without OOM; degraded-but-honest notice if
  the host can't support it.

**Cross-cutting (the "no regrets" gate):**
- A user can state, in one sentence each, **when to use which tier** — verified
  by a one-paragraph doc + in-portal copy that the QA persona reviews for clarity.
- Llama disclosure compliance: name begins `llama-`, "Built with Llama" shown,
  NOTICE bundles license + AUP. (Hard gate — required by the Llama 3.2 license.)

## Wedge

The smallest credible thing that proves the value, shippable in one sprint and
runnable on the developer's own machine with no cloud account:

**Ship minimalist (Llama-3.2-1B) as the auto-installing, zero-config default
and wire maximus deep (Qwen2.5-7B) as a one-command opt-in — validating the
existing v1.1 choices rather than reverting to TinyLlama/Mistral-Q2.**

Concretely, the wedge is: prove the two thresholds above on a real clean-machine
run, write the tier-selection copy, and confirm the AeroLLM-or-AirLLM fallback
path for the deep tier surfaces an honest notice. Nothing about TinyLlama or
2-bit Mistral ships. If a smaller deep artifact is genuinely needed, that's a
*follow-up* sprint with its own quality gate — not bundled into this one.

## Disconfirming evidence

Pre-committed signals that we chose wrong:

- **Minimalist too weak:** if the 10-prompt smoke set scores **< 8/10**, or two
  internal users independently say "Buddy feels dumb" in the first session, the
  default model is wrong (and notably, TinyLlama would score *worse* here — this
  is the metric that kills the task's proposal).
- **Maximus not worth it:** if deep mode fails to beat minimalist on **≥ 4/5**
  reasoning prompts, the upgrade is theater. A 2-bit Mistral is the most likely
  way to trip this wire.
- **Setup too heavy:** if clean-machine setup exceeds **15 min** or the default
  pull breaks on a 16 GB box, the zero-config promise is broken.
- **Tier confusion:** if users can't articulate when to use which, or pick
  maximus "just in case" and then complain about resource use, the framing failed.
- **License snag:** any Llama-disclosure miss is an immediate stop-ship.

## Displacement

Saying yes to this sprint means **AeroLLM CUDA-backend work and Nucleus
teacher-inference integration get less attention this cycle.** Specifically:

- The maximus deep tier leans on AeroLLM (mac/MLX) with AirLLM as the CUDA
  stopgap. Validating the tier here does *not* advance AeroLLM's CUDA backend —
  it documents the fallback. That CUDA work stays queued.
- aerollm-distill is the natural home for "make the deep model smaller without
  Q2 garbage." If we later want a sub-2.2 GB deep model, that's distill's job,
  and pulling it forward would displace distill's current roadmap. Flagging now
  so it's a conscious choice, not a surprise.
- The "nothing gets displaced" answer is false here: the AeroLLM team's time is
  the scarce resource and the deep tier depends on it.

## Recommended next step

**Proceed to `/architect` — with the model choices corrected to the v1.1 repo
reality (Llama-3.2-1B default, Qwen2.5-7B deep), not the task's TinyLlama /
Mistral-7B-Q2 proposal.**

The architect should design: (1) the clean-machine setup path and its failure
modes, (2) the maximus AeroLLM/AirLLM fallback and its honest-notice UX, and
(3) the tier-selection copy. The TinyLlama/Mistral-Q2 substitution is **rejected
on quality and consistency grounds** and should not enter the architecture
unless the user supplies a hard footprint constraint that the current models
provably cannot meet — in which case the answer is a Q4 7B, still not Q2.
