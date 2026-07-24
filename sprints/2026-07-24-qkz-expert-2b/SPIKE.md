# SPIKE — can we actually train + seal the QuKaiZen expert on this box?

**Date:** 2026-07-24 · **Verdict: GO, with one hard constraint (see Finding 3).**

Run before committing to the sprint, per the pre-committed disconfirmers in
`sprints/2026-07-22-distill-now/VISION.md`. Every claim below was executed on
Charlie's machine, not reasoned about.

---

## Finding 1 — Docker is a non-blocker (disconfirmer #1 does NOT fire)

VISION disconfirmer #1 said: *"The certifier won't run on Charlie's box in-sprint
… a docker-compose stack (NATS + orchestrator + certifier + trainer)."*

Measured:

| Check | Result |
|---|---|
| `docker info` | daemon **not running** |
| `docker` binary | **present** |
| `/Applications/OrbStack.app` | **installed** |
| nucleus `docker/docker-compose.yml` + `.dev.yml` | **present** |
| ports 8000 / 8005 / 8006 | all down (daemon off) |

So this is *"start OrbStack"*, not *"can't run the stack."* **Disconfirmer #1
does not fire.** The seal path stays in scope.

## Finding 2 — There is a native MLX path that needs no Docker at all

`qukaizen-nucleus/nucleus/trainer/mlx_trainer.py` exposes `MLXTrainer` +
`TrainingConfig`, and its own docstring states: *"this module is pure compute;
the service layer handles NATS publishing."*

- `TrainingConfig.model_name` accepts **any HF model id or local path** → a Gemma
  MLX base drops straight in.
- Real LoRA knobs (`lora_rank`, `lora_alpha`, `output_dir`).
- **No NATS/orchestrator dependency for the training step itself.**

`mlx_lm` is installed and importable **0.31.3** (arail venv) / **0.29.1**
(system python), on Apple Silicon.

**Implication:** training the expert does not require standing up the full
docker stack. Docker is needed only for the *certifier/seal* step. That splits
the sprint into a low-risk half (train, native) and a higher-risk half (seal).

## Finding 3 — ⚠ The trainer silently fabricates when mlx_lm is missing

This is the finding that should shape the whole sprint.

```python
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    logger.info("mlx_lm not installed — trainer will run in simulation mode. ...")
```

Docstring: *"falls back to a simulation mode that writes a **mock checkpoint**
and returns **realistic metrics** — allowing the full SSDP pipeline to run
end-to-end without hardware dependencies."*

That is the **exact failure class** the 2026-07-23 clean-experience sprint just
removed from the Researcher (invented metrics presented as measured). Here it is
worse, because the artifact is a *model*: a simulated run yields a mock adapter
plus plausible loss curves, and the downstream cert gates can pass on it.

**Strong evidence this already happened:**
`models/graduated/qkz-project-aware-2b-v1.0/` claims `status: graduated`, all
three cert gates passed (0.875 / 0.850 / 0.800), `adapter_size_mb: 15`,
`shipping: git-lfs` — yet the committed `adapters.safetensors` is **1210 bytes
of JSON metadata with no tensors** (relabeled `.placeholder` in WP4). That is
what a simulation-mode checkpoint looks like. The existing "graduated" expert is
almost certainly a simulated artifact.

**Sprint constraint (non-negotiable):** the run must *assert* `MLX_AVAILABLE` is
True and hard-fail otherwise. A simulated training run must never be able to
produce something labeled a trained model. Verify the emitted adapter has real
tensors (size + tensor count), not just that a file exists.

## Finding 4 — Licensing error to fix before anything is published

`models/graduated/qkz-project-aware-2b-v1.0/superskill-spec.yaml`:

```yaml
license: apache-2.0  # Inherited from Gemma 4 base
base_model: google/gemma-4-E2B-it
```

**Gemma is not Apache-2.0.** It is licensed under the Gemma Terms of Use. The
repo already bundles `licenses/GEMMA-TERMS-OF-USE.txt` and
`licenses/GEMMA-PROHIBITED-USE-POLICY.txt`, and `CLAUDE.md` documents the
disclosure obligation — so the spec contradicts both. Redistributing a
Gemma-derived model labeled Apache-2.0 is a real misstatement.

Per the live Terms (confirmed in CLAUDE.md): Gemma requires **"Built with
Gemma"** disclosure but **does not** require the model name to contain "Gemma" —
so `qkz-project-aware-2b` needs no rename. (Llama is the opposite: name must
start with "Llama".)

## Finding 5 — The speculative pairing is available today

Speculative decoding requires draft and target to share a tokenizer. Phase-0
research names this: *"requires a compatible draft model for every target
model."*

On disk in ollama: `gemma-4-26b-a4b` (14 GB, MoE 26B total / ~4B active). A
Gemma 2-3B expert is **vocabulary-compatible** with it → draft/verify works.
A Qwen or gpt-oss target would **not** pair with a Gemma draft.

This is why the base-model choice is Gemma: it is what makes the
"1-3B resident + aeroLLM for anything harder" story able to become real
speculative decoding later, rather than only tiered routing.

---

## Finding 6 — A0 LoRA-compatibility spike: **PASSED** (executed 2026-07-24)

Disconfirmer 1 asked whether `mlx_lm` can LoRA a *mixed* 4/8-bit OptiQ
checkpoint. Run end-to-end on the real base. **It does not fire.**

| Check | Result |
|---|---|
| Download `mlx-community/gemma-4-e2b-it-OptiQ-4bit` → `/Users/Shared/models/` | 4.9 GB on disk (4.0 GB LM + 908 MB vision tower) |
| `mlx_lm.load()` | **OK — 1.14 B params** (matches hub metadata; the vision tower is not loaded as text params) |
| Architecture | `Gemma4ForConditionalGeneration` — a VLM; `mlx_lm` loads the text LM only |
| LoRA train, 10 iters, 4 layers, 20-example corpus | **Ran.** Val loss **9.448 → 6.393**; train loss 9.113 → 7.138 |
| Trainable params | 1.704 M (0.037 % of 4628.6 M as counted incl. vision/PLE) |
| Peak memory (training) | **4.752 GB** |
| Throughput | 1274 tokens/sec at iter 10 |

**Emitted adapter passes the WC-A real-tensor check:**

| | this spike | the v1.0 "graduated" stub |
|---|---|---|
| bytes | **6,822,619** (6.8 MB) | **1,210** |
| tensors | **56**, all > 1000 elements | none (JSON metadata only) |
| params | 1.704 M | — |
| dtype / sample | float32 `(12288, 8)`, nonzero | — |

A **5,600× size difference.** The ARCHITECTURE A1 criteria (> 1 MB, tensor
count > 0, ≥1 float tensor with numel > 1000) separate real from simulated
cleanly — confirmed against both a genuine artifact and the known-bad stub.

**Consequences for the plan:**

- Base is **confirmed usable**; no fallback to `gemma-4-e2b-it-4bit` needed.
- ⚠ **WC-C (≤ 3 GB resident) is now the live risk, not LoRA compat.** The folder
  is 4.9 GB and training peaked at 4.75 GB. Training memory ≠ inference
  residency, but resident footprint must be *measured* before claiming the
  "1–3 B in memory" property. If it exceeds 3 GB, consider the text-only or
  plain 4-bit variant, or drop the vision tower.
- LoRA rank defaulted to 8 (`lora_a` shape `(12288, 8)`); A3's rank-16 plan is a
  deliberate step up, not the default.

## Verdict

**GO.** No disconfirmer fires fatally. Recommended shape:

1. **Phase A (low risk, native):** fix the license error; train the Gemma 2-3B
   expert on the QuKaiZen corpus via `MLXTrainer` with a hard `MLX_AVAILABLE`
   assert + real-tensor verification. No Docker required.
2. **Phase B (higher risk, gated):** stand up OrbStack + the nucleus stack and
   seal the artifact. If the certifier misbehaves, descope to "trained model +
   JSON run receipt, seal deferred" exactly as the distill-now VISION
   pre-committed — do not block Phase A on it.

**Open question for Phase A:** exact Gemma base id/quant to train from
(`google/gemma-4-E2B-it` was the prior base; an MLX-community 4-bit build is the
natural fit for `mlx_lm`). Resolve by checking what actually pulls before
committing corpus/GPU time.
