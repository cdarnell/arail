# A3 calibration run — 200 iters, before committing to a full fine-tune

**Date:** 2026-07-24 · **Verdict: DO NOT run the full fine-tune yet.** Two
blocking findings, both cheap to fix, both expensive to have discovered after a
full run.

Run locally (no GitHub Actions, per operator preference). Config: rank 16,
16 layers, batch 2, seq 1024, lr 1e-4, 200 iters, corpus
`sha256:5cc43a58…` (4,983 train / 553 holdout).

## What worked

| Metric | Value |
|---|---|
| Wall clock | **101 s** for 200 iters |
| Throughput | 2.0–2.5 it/s · ~1,100 tokens/s |
| Trainable params | 13.63 M (0.295 %) — rank 16 / 16 layers |
| Val loss | **8.483 → 2.711 → 2.449** (iters 1 / 100 / 200) |
| Adapter (A1-verified) | 54,554,030 bytes · 224 tensors · REAL |

**Full-run estimate:** 4,983 examples at batch 2 ≈ 2,492 iters/epoch ≈ **19 min
per epoch**; 3 epochs ≈ **~1 hour**. Cost is not a constraint here.

Loss falls steadily with no divergence — the optimization is healthy.

## ⛔ Finding 1 — the corpus uses the WRONG chat template

**This is the blocker.** Generation after fine-tuning is degenerate:

```
FINE-TUNED: "Thinking about ARAIL_AUTO_CHECKS in the context of ARAIL
             (AutoResearch/AutoResearch/AutoResearch/AutoResearch/…"
```

Root cause, confirmed by reading the model's own `chat_template.jinja`:

> `Template: Google Gemma 4 Canonical Chat Template … Fixed tool-calling loops,
> turn closures, and thinking content-ordering.`

It uses **`<|turn>` / `<|channel>` / `<|tool_call>`** markers and a *thinking
channel* — visible in the base model's own output (`<|channel>thought`).

`scripts/build_qkz_corpus.py` emits the older **Gemma 2/3** format
(`<start_of_turn>user … <end_of_turn>`). So every training example taught the
model a turn structure it does not use, damaging its native formatting — which
is exactly how you get loop-until-max-tokens output.

**Fix (A2 change):** build the training text with the tokenizer's own template
(`tokenizer.apply_chat_template(...)`) instead of a hardcoded string, so the
corpus can never drift from the model. Re-run calibration to confirm coherence
before the full run.

*Lesson worth keeping: loss went down beautifully while output quality went
down. Loss alone would have green-lit a broken model — the generation check is
what caught it.*

## ⚠ Finding 2 — WC-C (≤ 3 GB resident) is NOT met

Measured at inference, which the A0 spike could not answer:

| | Peak memory |
|---|---|
| Base model | **4.362 GB** |
| Base + adapter | **4.375 GB** |

The target in VISION was **≤ 3 GB resident**. Actual is ~4.4 GB — over by ~45 %.
The adapter itself costs almost nothing (+13 MB); the base is simply bigger than
the "1.14 B params" headline implies, because this checkpoint is a VLM
(`Gemma4ForConditionalGeneration`) carrying a 908 MB vision tower plus per-layer
embeddings.

Three honest options, for the operator to choose:

1. **Revise the target to ≤ 5 GB.** 4.4 GB resident still leaves the deep tier
   the lion's share on a 128 GB box, and keeps the Gemma family (so speculative
   pairing with `gemma-4-26b-a4b` stays available). Lowest friction.
2. **Strip the vision tower** — text-only variant; smaller, but needs verifying
   `mlx_lm` still loads and LoRAs it.
3. **Drop to a smaller base** — gives up Gemma-family speculative pairing, which
   was the reason for choosing Gemma at all.

Recommendation: **option 1**, and record the real number rather than quietly
keeping a target we miss.

Training peak memory was **18.0 GB** (16 layers, batch 2, seq 1024) — fine on
this box, but note it scales with layers × batch × seq, not with the 4.4 GB
inference figure.

## ⚠ Finding 3 — sequence truncation

Several examples exceed the 1024-token window (longest observed: **1,394**) and
are silently truncated, so those answers lose their tails and teach incomplete
responses. Fix by raising `max_seq_length` to ~1536 and/or lowering
`MAX_ANSWER_CHARS` in the corpus builder so pairs fit whole.

## Next actions (in order)

1. Fix the corpus to emit the model's native template (A2 change) — **blocking**.
2. Re-run this 200-iter calibration; require *coherent* generation, not just
   falling loss.
3. Decide WC-C: revise the target to ≤ 5 GB, or change the base.
4. Raise `max_seq_length` / cap answer length to stop truncation.
5. Only then run the full fine-tune (~1 h for 3 epochs).
