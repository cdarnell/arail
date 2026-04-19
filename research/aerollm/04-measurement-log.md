# 04 — Measurement Log

*Append-only. One row per experiment. Don't delete, don't edit past rows — if a measurement was wrong, add a new row that supersedes it and say so in the notes.*

The whole point of this folder is that **numbers replace guesses**. Guesses live in `00-product-vision.md` and `02-batching-strategy.md`. Measurements land here.

---

## Row schema

Each experiment gets one Markdown row. Copy-paste the template below.

Fields:

- **ID** — short unique ID. Convention: `YYYY-MM-DD-##` (e.g., `2026-04-18-01`).
- **Date** — ISO date of the run.
- **Hypothesis** — one sentence. What do you think will happen?
- **Hardware** — machine name (e.g., `M5-24GB`, `Linux-96GB-RTX4090`), plus relevant constraints.
- **Backend** — `aerollm-cuda`, `aerollm-mlx`, or `aerollm-<branch>@<sha>` when testing a non-main branch.
- **Model** — full HF ID + precision (e.g., `InferenceIllusionist/gpt-oss-20b-MLX-4bit`).
- **Knobs** — only the knobs that differ from the default in `config/tuning.yml` or `config/tuning-mlx.yml`.
- **Batch N** — prompts in the batch.
- **Prompt** — short description of the prompt set (e.g., "verdagon bench prompt", "64-token greedy from tuning-mlx baseline_prompt").
- **Max tokens** — output budget per prompt.
- **Runs** — how many repetitions. Report median.
- **Metric: t_load/layer** — measured load time per layer (ms), if isolable.
- **Metric: t_compute/layer** — measured compute time per layer (ms).
- **Metric: tok/sec per prompt** — 1 / time-per-token-per-prompt.
- **Metric: tok/sec aggregate** — N × tok/sec per prompt.
- **Metric: peak RAM** — GB, unified or host side.
- **Metric: peak VRAM** — GB (CUDA only).
- **Metric: quality** — perplexity on held-out or judge-rated pass rate. Leave blank if quality wasn't checked.
- **Status** — `ok`, `oom`, `crash`, `partial` (one token but not full decode).
- **Commit / branch** — git ref so the row can be reproduced.
- **Notes** — anything surprising, anomalies, follow-up questions.
- **Raw file** — path to the JSONL line in `lab/data/aerollm-bench.jsonl` or `lab/data/mlx-bench.jsonl` if one exists.

---

## Row template (copy this)

```markdown
### <YYYY-MM-DD-##> — <one-line summary>

- **Hypothesis:** <one sentence>
- **Hardware:** <machine>
- **Backend:** <backend>
- **Model:** <hf_id + precision>
- **Knobs:** <diffs from default, or "defaults">
- **Batch N:** <int>
- **Prompt:** <short description>
- **Max tokens:** <int>
- **Runs:** <int>
- **t_load/layer:** <ms or "n/a">
- **t_compute/layer:** <ms or "n/a">
- **tok/sec per prompt:** <float>
- **tok/sec aggregate:** <float>
- **Peak RAM:** <GB>
- **Peak VRAM:** <GB or "n/a">
- **Quality:** <perplexity / judge pass rate / "not measured">
- **Status:** <ok | oom | crash | partial>
- **Commit:** <sha or branch>
- **Raw file:** <path or "n/a">
- **Notes:** <free text>
```

---

## Rows

### 0000-00-00-00 — (seed row, no data)

- **Hypothesis:** — (placeholder)
- **Notes:** The first actual measurement row lands when Experiment 1 from `02-batching-strategy.md` runs. Until then, `00-product-vision.md` and `02-batching-strategy.md` are *all guesses and table-shape*. That's honest: we write the guess-tables explicitly so the measurements can refute them.

---

## Downstream pipeline metrics (once end-to-end runs)

Once the distillation pipeline runs end-to-end (Experiment 4 in `02-batching-strategy.md`), these additional fields start appearing per row — or we add pipeline-level rows separate from inference-level rows.

- **Examples produced** — count of `(prompt, rationale, answer)` triples that survived the swarm filter.
- **Swarm rejection rate** — fraction rejected by critic / red-team / judge agents. Broken out per stage.
- **Corpus tokens/day** — aggregate teacher tokens that made it into the final corpus (examples × avg output length × (1 - rejection rate)).
- **Student eval (when trained)** — benchmark pass rate on held-out eval for the student model trained on this corpus slice.

---

## Cross-reference discipline

When a measurement row contradicts a guess in `00-product-vision.md` or `02-batching-strategy.md`, **update those docs with a superseding note pointing to this row ID**. Don't silently correct the guess. The point is to preserve the trail of what we thought → what we measured → what we learned.

Same for `03-parallel-work.md`: if one of our runs disproves a claim about a competitor (e.g., KTransformers underperforms on MoE in a scenario where we thought it'd dominate), land that here and link back from `03-`.

---

## The one automation we should build

Autoresearch (see `docs/tuning-loop.md`) already writes to `lab/data/aerollm-bench.jsonl` and `lab/data/mlx-bench.jsonl`. A small Markdown-summarizer that reads those JSONL files and appends rows *here* (in the schema above) would remove the manual-copy step. Low priority until we're running sweeps frequently enough for hand-copying to hurt.
