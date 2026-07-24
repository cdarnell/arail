# ARCHITECTURE — Phase A: train `qkz-expert` (~1.1B, Gemma-4 E2B)

Build spec for [`VISION.md`](./VISION.md), gated by [`SPIKE.md`](./SPIKE.md).
Every external fact here was verified on the live hub or on disk — see SPIKE.

## Ground truth

| Fact | Value | Source |
|---|---|---|
| Base | `mlx-community/gemma-4-e2b-it-OptiQ-4bit` | HF hub |
| Params | **1,141.2 M** (~1.1 B) | HF hub |
| Task / library | `text-generation` / `mlx` | HF hub |
| License | **`gemma`** (Gemma Terms of Use) | HF hub |
| Trainer | `qukaizen-nucleus/nucleus/trainer/mlx_trainer.py` — `MLXTrainer` + `TrainingConfig`, pure compute, no NATS | SPIKE F2 |
| `mlx_lm` | **0.31.3** installed (arail venv) | SPIKE F2 |
| Docker needed for Phase A | **No** | SPIKE F2 |
| Speculative verifier on disk | `gemma-4-26b-a4b-it-4bit`, `gemma-4-31b-it-4bit` (`/Users/Shared/models`) | disk |
| MTP draft head | `mlx-community/gemma-4-E2B-it-qat-assistant-4bit` — **12.4 M**, arch `gemma4_assistant` | HF hub |

Checkpoints go to `/Users/Shared/models/` per the machine convention
(`docs/models-on-disk.md`); ARAIL reads them via `ARAIL_MODELS_DIR`.

---

## A0 — Day-one compatibility spike (BLOCKING, ~30 min)

Disconfirmer 1 is the pivotal unknown: OptiQ is *mixed* 4/8-bit, and `mlx_lm`
LoRA may refuse it. Resolve before any corpus work.

1. `hf download mlx-community/gemma-4-e2b-it-OptiQ-4bit --local-dir /Users/Shared/models/gemma-4-e2b-it-OptiQ-4bit`
2. Generate a throwaway 20-example JSONL corpus.
3. Run `MLXTrainer` for ~10 iters.
4. **Assert:** `MLX_AVAILABLE is True`, and the emitted adapter contains real
   tensors.

**RESULT (2026-07-24): PASSED — see [`SPIKE.md`](./SPIKE.md) Finding 6.**
LoRA trains on the OptiQ mixed 4/8-bit quant; val loss 9.448 → 6.393 in 10 iters;
emitted adapter is 6.8 MB / 56 real tensors (vs the 1210-byte known-bad stub).
`mlx_lm` loads the text LM at 1.14 B params. **No fallback base needed** — the
`gemma-4-e2b-it-4bit` / bf16 contingency is unused. Proceed to A1.

⚠ **Risk moved:** LoRA compatibility is settled, so **WC-C (≤ 3 GB resident) is
now the live risk.** The base folder is 4.9 GB and training peaked at 4.75 GB.
Training memory ≠ inference residency — measure resident footprint in A5 before
claiming the "1–3 B in memory" property; if it exceeds 3 GB, evaluate a
text-only/plain-4bit variant or strip the vision tower.

---

## A1 — The anti-fabrication guard (write FIRST)

The single most important deliverable. SPIKE F3: the trainer silently degrades to
simulation mode and emits a mock checkpoint with realistic metrics — the likely
origin of the existing 1.2 KB "graduated" stub.

New `scripts/train_qkz_expert.py` (in arail; imports nucleus' trainer) MUST:

```python
from nucleus.trainer.mlx_trainer import MLXTrainer, TrainingConfig, MLX_AVAILABLE

if not MLX_AVAILABLE:
    raise SystemExit(
        "REFUSING TO TRAIN: mlx_lm unavailable, so nucleus' MLXTrainer would "
        "silently produce a SIMULATED adapter with realistic-looking metrics. "
        "That is how the 1.2KB qkz-project-aware-2b stub was almost certainly "
        "produced. Install mlx-lm and re-run."
    )
```

and after training, `verify_real_adapter(path)`:

- file exists and is **> 1 MB** (the known-bad stub is 1210 B),
- loads as safetensors with **tensor count > 0**,
- contains ≥1 float tensor with `numel > 1000`,
- size is plausible for `lora_rank` (order-of-magnitude check).

Any failure → delete the artifact and exit non-zero. **Never leave a
mock adapter on disk that a later step could mistake for real.**

Mirror of the WP5 rule from 2026-07-23: *measured, or it does not exist.*

---

## A2 — Corpus

`scripts/build_qkz_corpus.py` → `lab/data/corpus/qkz-expert-<sha>.jsonl`

- Sources: `qukaizen-aerollm`, `qukaizen-arail`, `qukaizen-dac`,
  `qukaizen-nucleus` — code + `docs/` + `CLAUDE.md` + ADRs.
- **Exclude:** `.venv`, `node_modules`, `lab/` runtime state, `.git`, weights,
  anything matching the repos' `.gitignore`, and **secrets** (`.env`,
  `secrets.env`, `lab.conf`) — a fine-tune memorizes what it is shown.
- Format: instruction pairs, not raw dumps (disconfirmer 3 — raw dumps degrade
  instruction-following). Derive Q&A from docstrings, ADR decisions, README
  sections, function signatures.
- Emit `corpus_sha256` + per-source file counts into the receipt.
- Hold out ~10% as the eval set, **never trained on**.

## A3 — Training

`TrainingConfig(model_name=<A0 base>, lora_rank=16, lora_alpha=32, output_dir=/Users/Shared/models/qkz-expert-v0.1/adapters)`

Start conservative (rank 16); tune only if WC-B fails. Log real loss curves —
if `MLX_AVAILABLE` gating is honored these are genuine.

## A4 — Evaluation (reuse, don't rebuild)

Score with `arail.research.mini_experiments` from the 2026-07-23 sprint:

- Fine-tuned vs **untouched base**, same held-out QuKaiZen questions.
- **Code-computed metrics only** — no model self-scoring (that engine already
  enforces this): keyword/identifier hit-rate against known-correct answers,
  format compliance, latency, tok/s.
- Also run held-out **general** prompts to detect catastrophic forgetting
  (disconfirmer 3).
- Report `measured` / `cannot_run` provenance exactly as the engine does.

**WC-B passes only if the fine-tune beats the base on a computed metric.**

## A5 — Register + ship honestly

- Write `models/graduated/qkz-expert-v0.1/superskill-spec.yaml` with the **real**
  base, corpus SHA, **actual** adapter bytes, `license: gemma-terms-of-use`,
  `license_files: [licenses/GEMMA-TERMS-OF-USE.txt, licenses/GEMMA-PROHIBITED-USE-POLICY.txt]`,
  and **"Built with Gemma"** (required; no rename needed — unlike Llama).
- `models/ai-eng/Modelfile.qkz-expert` persona wrap; register via the ARAIL
  registry as the `fast` (tier 0) profile.
- Commit `RECEIPT.json`: base id, corpus SHA, config, seed, adapter SHA256,
  `mlx_lm` version, host, timestamps.
- Do **not** claim cert gates that did not run on real tensors.

## A6 — Docs

Update `docs/models-on-disk.md` (a fifth artifact location: the expert),
`CLAUDE.md` tier-0 description, and note the speculative tension from VISION so
nobody later fine-tunes the draft head and wonders why acceptance dropped.

---

## Deliberately NOT in Phase A

| Deferred | Why |
|---|---|
| Ed25519 seal / certifier / OrbStack | Phase B. Docker works (SPIKE F1) — deferred by choice to bound risk. |
| Speculative wiring (draft + 26B verifier, MTP head) | Needs the VISION tension resolved; Phase A's eval informs it. |
| Compaction, "Distill now" button | `2026-07-22-distill-now` scope. |
| Retiring `qkz-project-aware-2b-v1.0` | Leave the stub labeled `.placeholder`; superseding it is A5's job, deleting it is not. |

## Verification (sprint gate)

```bash
# WC-A — real tensors, and simulation refused
python scripts/train_qkz_expert.py --verify-only /Users/Shared/models/qkz-expert-v0.1/adapters
wc -c /Users/Shared/models/qkz-expert-v0.1/adapters/adapters.safetensors   # >> 1210
# WC-C — resident footprint + it answers
./arailctl doctor          # qkz-expert as tier 0, healthy
# WC-D — honest spec
grep -E "license|adapter_size|base_model" models/graduated/qkz-expert-v0.1/superskill-spec.yaml
```

Plus: `pytest tests/` green, and a new
`tests/test_train_guard.py` asserting the trainer **refuses** to emit an artifact
when `MLX_AVAILABLE` is False.
