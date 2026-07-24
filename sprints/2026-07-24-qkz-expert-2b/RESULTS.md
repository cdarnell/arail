# A3/A4 results — the full fine-tune, and what it actually taught

**Date:** 2026-07-24 · Run: 5,000 iters (~2 epochs), rank 16, 16 layers,
batch 2, seq 1536, lr 1e-4, dropout 0.05. Corpus `sha256:ecb65002…`
(4,983 train / 553 holdout). All local, ~40 min, peak train mem 26.95 GB.

**Verdict: the pipeline is sound and the model improved measurably — but it
learned QuKaiZen *voice*, not QuKaiZen *facts*. Do not ship this as a
knowledge source.**

## 1. It overfit, and the last checkpoint is not the best

| iter | 1500 | 1750 | **3000** | 4000 | 4750 | 5000 |
|---|---|---|---|---|---|---|
| val loss | 1.989 | 1.940 | **1.902 (best)** | 2.151 | 2.196 | **2.329 (worst since 500)** |

Train loss fell to **1.643** while validation *rose* — textbook overfitting on
4,983 examples with 13.6 M trainable params.

`mlx_lm` writes the FINAL weights to `adapters.safetensors`. Taking that default
(what most pipelines do) ships the worst-validation checkpoint. `save_every: 500`
is what made a real choice possible.

## 2. …but by the task metric, the overfit checkpoint scores *best*

WC-B, measured: token-overlap F1 against reference answers, 20 held-out
questions, temperature 0, code-computed (no model self-scoring).

| variant | F1 | vs base |
|---|---|---|
| Base (no adapter) | 0.0623 | — |
| Best-val ckpt (3000) | 0.0925 | +48 % |
| **Final ckpt (5000)** | **0.1527** | **+145 %** |

So val loss and task score **disagree**, and the metric prefers the checkpoint
val loss rejects.

## 3. Why they disagree — and why the metric is not enough

Val loss measures next-token prediction. Token overlap measures shared
vocabulary. The overfit model absorbed more QuKaiZen phrasing, so it scores
higher on overlap while being *less* well-calibrated.

Read the actual generations for *"what is `ARAIL_AUTOCHECKS` for?"*:

- **best-val (3000):** degenerates — *"The 15-question probe. / benchmark. /
  confidence report. / regression suite. / smoke test…"*
- **final (5000):** fluent and wrong — *"Per-check + warn + fix on every
  user-provided model response. Silently passes through the local-first path…"*

Ground truth: `ARAIL_AUTOCHECKS` is the master switch (default off) gating
background probes/warmers so the lab boots quiet.

**Neither is correct.** The final checkpoint scores 2.4× the base *by producing
confident hallucinations in fluent QuKaiZen dialect.* That is arguably worse
than the base model, which at least hedged.

> **On the letter of WC-B this PASSES** (a code-computed metric improved, by a
> lot). On the intent it FAILS. Reporting only the F1 would be exactly the
> failure this sprint was created to eliminate: *a number that looks good is not
> a working thing.* Recording both.

## 4. The cause is not the corpus

The obvious hypothesis — the fact was missing — is wrong. `ARAIL_AUTOCHECKS`
appears **twice in train.jsonl**, and the training answer is verbatim correct
(it is the `autochecks.py` module docstring).

The model was shown the right answer and still cannot recall it. That is the
expected behaviour of LoRA on a ~1.1 B model: **13.6 M low-rank params over a
fact seen 1–2 times do not produce reliable factual recall.** LoRA adapts
*style, format and register* well; it is a poor instrument for knowledge
injection. Getting facts in via weights would need orders more repetition, full
fine-tuning, or a much larger base — all of which fight the "small, resident"
goal.

This is VISION disconfirmer 2 firing, as pre-committed: *"If WC-B shows the
fine-tune does not beat the base [in substance] … keep the expert as a
specialist … Do not ship a downgrade and call it a win."*

## 5. What to do instead — ARAIL already has the right mechanism

Facts belong in **retrieval**, not weights. ARAIL already ships exactly that:
the PKB with the Compiled-KB gate and `search_for_agents` (human-approved
knowledge only, hardened in the 2026-07-23 sprint).

The coherent architecture is therefore:

| Need | Mechanism |
|---|---|
| Fast, resident, on-register QuKaiZen voice | **this fine-tune** (measurably better: +145 % F1) |
| Correct QuKaiZen facts | **RAG over the approved PKB** — already built |
| Hard reasoning | escalate to aeroLLM (unchanged) |

That also removes the retraining treadmill: today's corpus is stale the moment
the code changes, whereas the PKB re-indexes.

## 6. Status against the win conditions

| | |
|---|---|
| **WC-A** genuinely trained | ✅ A1-verified REAL — 54,554,030 B, 224 tensors, 13.6 M params |
| **WC-B** beats base on a computed metric | ⚠️ **letter: PASS** (+145 % F1) · **intent: FAIL** (answers are wrong) |
| **WC-C** ≤ 3 GB resident | ❌ **4.375 GB** measured — recommend revising the target to ≤ 5 GB |
| **WC-D** honest provenance | ✅ this document; no cert-gate claims made |
| **WC-E** reproducible | ✅ corpus sha + template fingerprint + config committed |

## 7. Recommended next step

**Do not register this as tier 0 on its own.** Two options:

1. **Ship it as voice + wire RAG** (recommended) — keep the adapter for register,
   serve facts from the approved PKB. Uses infrastructure that already exists.
2. **Re-scope to a narrower skill** where style *is* the product (commit
   messages, code review tone) and drop the "knows the codebase" claim.

Either way the honest headline is: *we can train a real adapter, cheaply and
reproducibly, and it makes the model sound like QuKaiZen — it does not make it
know QuKaiZen.*
